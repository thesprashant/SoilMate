"""Persist advice with evidence shared by typed and live voice conversations."""
import re
from datetime import date, timedelta
from app.db.repository import save_advisory
from app.services.references import crop_reference
from google.genai import types


schedule_decl = types.FunctionDeclaration(
    name="record_crop_schedule",
    description="Record a crop schedule only after fetching query_crop_database. Quote the source exactly. For a dated calendar, use the farmer's explicitly stated sowing_date (YYYY-MM-DD) and days_after_sowing only when the exact quote supports that interval. Leave unsupported dates out.",
    parameters=types.Schema(type="OBJECT", properties={
        "crop": types.Schema(type="STRING"),
        "sowing_date": types.Schema(type="STRING", description="Farmer-provided sowing date in YYYY-MM-DD format; omit if unknown."),
        "entries": types.Schema(type="ARRAY", items=types.Schema(type="OBJECT", properties={
            "stage": types.Schema(type="STRING", enum=["sowing", "harvesting", "irrigation", "fertilizer", "maintenance"]),
            "days_after_sowing": types.Schema(type="INTEGER", description="Days after sowing explicitly supported by the quote; omit for undated guidance."),
            "guidance": types.Schema(type="STRING", description="Plain-language summary in the farmer's language; no new numbers."),
            "quote": types.Schema(type="STRING", description="Exact supporting excerpt from fetched reference_text."),
            "source": types.Schema(type="STRING", description="Exact URL of the fetched reference.")
        }, required=["stage", "guidance", "quote", "source"]))
    }, required=["crop", "entries"])
)


def _wheat_irrigation_stage(ref, quote):
    """Recognize the named stage rows under TNAU's wheat irrigation heading."""
    if ref.get("source") != "https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html":
        return False
    text = ref.get("reference_text", "")
    heading = text.find("Wheat crop requires minimum of 5 irrigations at the following critical stages.")
    end = text.find("Crown root initiation and flowering are the most critical stages.", heading + 1)
    if heading < 0 or end < 0 or quote not in text[heading:end]:
        return False
    return bool(re.fullmatch(r"(?:II|III|IV|V)\s*[-–]\s*[A-Za-z ]+\s*:\s*\d{1,3}\s*[-–]\s*\d{1,3}\s*DAS", quote, re.IGNORECASE))


def validate_schedule(args, traces, user_text=""):
    refs = [t["outputs"] for t in traces if t["tool"] == "query_crop_database" and t["outputs"].get("reference_text")]
    crop = str(args.get("crop", "")).strip().lower()
    crop = "rice" if crop == "paddy" else crop
    entries = args.get("entries", [])
    if not entries or len(entries) > 20:
        return {"error": "Supply 1-20 source-supported schedule entries."}
    anchor = None
    raw_anchor = str(args.get("sowing_date") or "")
    if raw_anchor:
        try:
            proposed = date.fromisoformat(raw_anchor)
            numeric_dates = {raw_anchor, proposed.strftime("%d/%m/%Y"), proposed.strftime("%d-%m-%Y"), proposed.strftime("%d.%m.%Y")}
            if any(value in user_text for value in numeric_dates):
                anchor = proposed
        except ValueError:
            pass
    verified = []
    rejected = 0
    stage_words = {"sowing": r"\b(?:sow\w*|plant\w*|seed\w*|tubers?)\b",
                   "harvesting": r"\bharvest\w*\b", "irrigation": r"\b(?:irrigat\w*|water\w*)\b",
                   "fertilizer": r"\b(?:fertili[sz]\w*|manure|nitrogen|phosph\w*|potash|top.?dress\w*)\b",
                   "maintenance": r"\b(?:hoe\w*|hoeing|weed\w*|earth\w*)\b"}
    for entry in entries:
        quote = " ".join(str(entry.get("quote", "")).split())
        ref = next((r for r in refs if r["source"] == entry.get("source") and r["crop"] == crop and len(quote) >= 15 and quote in r["reference_text"]), None)
        stage = entry.get("stage")
        matching_stage = ref and stage in stage_words and (re.search(stage_words[stage], quote, re.IGNORECASE) or (stage == "irrigation" and _wheat_irrigation_stage(ref, quote)))
        if not matching_stage:
            rejected += 1
            continue
        guidance = str(entry.get("guidance", ""))
        if set(re.findall(r"\d+(?:\.\d+)?", guidance)) - set(re.findall(r"\d+(?:\.\d+)?", quote)):
            rejected += 1
            continue
        item = {"stage": entry["stage"], "guidance": guidance[:1500], "quote": quote[:3000], "source": ref["source"], "retrieved_at": ref["retrieved_at"], "coverage": ref["coverage"]}
        if stage == "irrigation" and _wheat_irrigation_stage(ref, quote):
            interval = re.search(r"(\d{1,3})\s*[-–]\s*(\d{1,3})\s*DAS", quote, re.IGNORECASE)
            start, end = map(int, interval.groups())
            if 0 <= start <= end <= 730:
                item["days_after_sowing"] = start
                item["days_after_sowing_end"] = end
                if anchor:
                    item["date"] = (anchor + timedelta(days=start)).isoformat()
                    item["date_end"] = (anchor + timedelta(days=end)).isoformat()
        offset = entry.get("days_after_sowing")
        if offset is None:
            explicit_interval = re.search(r"\b(\d{1,3})\s+days?\s+(?:after|from)\s+(?:sowing|planting)\b", quote, re.IGNORECASE)
            if explicit_interval:
                offset = int(explicit_interval.group(1))
        if anchor and isinstance(offset, int) and not isinstance(offset, bool) and 0 <= offset <= 730:
            # A numeric mention alone is insufficient: require it to be expressed in days.
            day_pattern = rf"\b{offset}\s*(?:-\s*\d+\s*)?(?:days?|day)\b"
            if re.search(day_pattern, quote, re.IGNORECASE) and re.search(r"\b(?:after|from)\s+(?:sowing|planting)\b", quote, re.IGNORECASE):
                item["date"] = (anchor + timedelta(days=offset)).isoformat()
                item["days_after_sowing"] = offset
        verified.append(item)
    if not verified:
        result = {"error": "No schedule entries matched the crop reference. Retry with exact, uninterrupted excerpts and matching stages.", "rejected_count": rejected}
        if refs:
            result["reference_text"] = refs[0]["reference_text"]
            result["source"] = refs[0]["source"]
        return result
    return {"status": "partial" if rejected else "success", "crop": crop, "entries": verified, "rejected_count": rejected,
            "note": "Regional reference guidance. Check variety, sowing method and local applicability with an extension worker."}


async def schedule_references(args, current_traces, history):
    """Resolve matching reference evidence from this session, or fetch it on demand."""
    crop = str(args.get("crop", "")).strip().lower()
    crop = "rice" if crop == "paddy" else crop
    prior = [trace for message in history if message.get("role") == "assistant"
             for trace in (message.get("tool_calls") or []) if isinstance(trace, dict)]
    references = [trace for trace in current_traces + prior
                  if trace.get("tool") == "query_crop_database" and isinstance(trace.get("outputs"), dict)
                  and trace["outputs"].get("crop") == crop and trace["outputs"].get("reference_text")]
    if references or not crop:
        return references
    result = await crop_reference(crop=crop)
    return [{"tool": "query_crop_database", "inputs": {"crop": crop}, "outputs": result}] if result.get("reference_text") else []


async def persist_advice(session_id, language, content, profile, traces, user_text=""):
    evidence = [t for t in traces if t["tool"] != "update_farmer_profile"]
    if not evidence or not content:
        return None
    refs = [t["outputs"] for t in traces if t["tool"] == "query_crop_database" and t["outputs"].get("crop")]
    plans = [t["outputs"] for t in traces if t["tool"] == "record_crop_schedule" and not t["outputs"].get("error")]
    entries = [entry for plan in plans for entry in plan.get("entries", [])]
    def result(tool):
        return next((t["outputs"] for t in reversed(traces) if t["tool"] == tool), None)
    weather = result("get_weather")
    record = await save_advisory(
        session_id=session_id, language=language, full_advisory_text=content,
        crop_name=(plans[-1].get("crop") if plans else None) or (refs[-1]["crop"] if refs else profile.get("primary_crop")) or "Farm guidance",
        location_name=profile.get("location_name"), latitude=profile.get("latitude"), longitude=profile.get("longitude"),
        sowing_window="\n".join(e["guidance"] for e in entries if e["stage"] == "sowing") or None,
        harvesting_window="\n".join(e["guidance"] for e in entries if e["stage"] == "harvesting") or None,
        irrigation_schedule=[e for e in entries if e["stage"] == "irrigation"],
        fertilizer_schedule=[e for e in entries if e["stage"] == "fertilizer"],
        protective_alerts=(weather or {}).get("alerts", []),
        soil_metrics=result("get_soil_data"), weather_summary=weather, market_summary=result("get_mandi_prices"),
        evidence={"tools": evidence, "schedule": entries, "note": "AI synthesis of tool evidence; review the sources, scope and missing data before acting."}
    )
    return record["id"]
