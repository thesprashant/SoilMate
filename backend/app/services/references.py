"""Fetch official reference material; never substitute a local mock catalog."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import httpx

# URL routing is configuration, not an agronomic dataset. Contents are fetched live.
REFERENCES = {
    "wheat": "https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html",
    "rice": "https://agritech.tnau.ac.in/govt_schemes_services/aas/paddy.html",
    "potato": "https://agritech.tnau.ac.in/horticulture/horti_vegetables_potato.html",
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


async def crop_reference(crop="", **filters):
    crop = str(crop).strip().lower()
    crop = "rice" if crop == "paddy" else crop
    url = REFERENCES.get(crop)
    if not url:
        return {"status": "unavailable", "error": "Please specify a supported crop." if not crop else "No verified reference is configured for this crop.", "supported_crops": list(REFERENCES)}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url)
            response.raise_for_status()
        parser = TextParser()
        parser.feed(response.text)
        text = " ".join(" ".join(parser.parts).split())[:24000]
        if len(text) < 100:
            raise ValueError("Empty reference")
        return {"status": "success", "crop": crop, "reference_text": text,
                "source": url, "retrieved_at": timestamp(), "data_kind": "official_reference",
                "coverage": "TNAU regional guidance; verify applicability to the farmer's state, variety and growing method. Not a current weather forecast.",
                "publication_date": "Not established; retrieval time is not publication time."}
    except (httpx.HTTPError, ValueError):
        return {"status": "unavailable", "error": "Official crop reference could not be retrieved. No planting or harvest dates have been substituted.", "source": url, "retrieved_at": timestamp()}
