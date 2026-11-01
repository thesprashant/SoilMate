from datetime import datetime, timezone
import math
import httpx
from app.config import settings
from app.services.references import timestamp

async def get_mandi_prices(state: str, commodity: str):
    current_resource_id = "35985678-0d79-46b4-9ed6-6f13308a1d24"
    resource_ids = list(dict.fromkeys((current_resource_id, settings.data_gov_resource_id)))
    source = f"https://api.data.gov.in/resource/{current_resource_id}"
    result = {"commodity": commodity, "state": state, "markets": [], "best_market": None,
              "total_found": 0, "source": source, "retrieved_at": timestamp(), "data_kind": "reported_market_quotes"}
    if not settings.data_gov_api_key:
        return {**result, "status": "unavailable", "error": "Mandi prices require DATA_GOV_API_KEY.", "note": "No prices substituted."}
    params = {"api-key": settings.data_gov_api_key, "format": "json", "limit": 100, "filters[commodity]": commodity.strip()}
    if state.strip():
        params["filters[state]"] = state.strip()
    try:
        records = None
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "SoilMate/1.0"}) as client:
            for resource_id in resource_ids:
                candidate = f"https://api.data.gov.in/resource/{resource_id}"
                try:
                    response = await client.get(candidate, params=params)
                    response.raise_for_status()
                    records = response.json().get("records", [])
                    source = candidate
                    break
                except (httpx.HTTPError, ValueError, TypeError):
                    continue
        if records is None:
            raise ValueError("No valid data.gov.in response")
        markets = []
        for record in records:
            r = {k.lower(): v for k, v in record.items()}
            try:
                if state and r.get("state", "").casefold() != state.casefold():
                    continue
                if r.get("commodity", "").casefold() != commodity.strip().casefold():
                    continue
                low, high, modal = (float(r[k]) for k in ("min_price", "max_price", "modal_price"))
                if not all(math.isfinite(v) and v > 0 for v in (low, high, modal)) or not low <= modal <= high:
                    continue
                date = datetime.strptime(r["arrival_date"], "%d/%m/%Y").date()
                age = (datetime.now(timezone.utc).date() - date).days
                if age < 0:
                    continue
                markets.append({"market": r["market"], "district": r.get("district", ""), "state": r["state"],
                                "commodity": r["commodity"], "variety": r.get("variety", ""), "min_price": low,
                                "max_price": high, "modal_price": modal, "date": date.isoformat(), "stale": age > 3})
            except (ValueError, TypeError, KeyError):
                continue
        markets.sort(key=lambda m: (m["date"], m["modal_price"]), reverse=True)
        fresh = [m for m in markets if not m["stale"]]
        return {**result, "source": source, "markets": markets[:20], "best_market": max(fresh, key=lambda m: m["modal_price"]) if fresh else None,
                "total_found": len(markets), "status": "success" if markets else "unavailable",
                "error": None if markets else "No valid quotes for the requested commodity and state.",
                "note": "Reported arrival dates are shown. Quotes over three days old are marked stale. Best price compares only returned fresh quotes; transport, grade and market coverage differ."}
    except (httpx.HTTPError, ValueError, TypeError):
        return {**result, "status": "unavailable", "error": "Mandi service could not be reached or returned invalid data.", "note": "No prices substituted."}
