import re
from typing import Dict, Tuple, Optional, List

# Mapping of ISO codes to native and English names
SUPPORTED_INDIAN_LANGUAGES: Dict[str, Dict[str, str]] = {
    "hi": {"name": "Hindi", "native": "हिन्दी", "code": "hi"},
    "te": {"name": "Telugu", "native": "తెలుగు", "code": "te"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "code": "ta"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "code": "kn"},
    "bn": {"name": "Bengali", "native": "বাংলা", "code": "bn"},
    "mr": {"name": "Marathi", "native": "मराठी", "code": "mr"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "code": "gu"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "code": "pa"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "code": "ml"},
    "od": {"name": "Odia", "native": "ଓଡ଼ିଆ", "code": "od"},
    "ur": {"name": "Urdu", "native": "اردو", "code": "ur"},
    "en": {"name": "English", "native": "English", "code": "en"}
}

# Unicode Script Ranges
UNICODE_SCRIPT_RANGES = [
    (0x0900, 0x097F, "Devanagari"),  # Hindi, Marathi, Nepali, Sanskrit
    (0x0C00, 0x0C7F, "Telugu"),
    (0x0B80, 0x0BFF, "Tamil"),
    (0x0C80, 0x0CFF, "Kannada"),
    (0x0980, 0x09FF, "Bengali"),
    (0x0A80, 0x0AFF, "Gujarati"),
    (0x0A00, 0x0A7F, "Gurmukhi"),     # Punjabi
    (0x0D00, 0x0D7F, "Malayalam"),
    (0x0B00, 0x0B7F, "Odia"),
    (0x0600, 0x06FF, "Arabic"),       # Urdu
]

# Marathi-specific grammatical markers vs Hindi
MARATHI_MARKERS = ["आहे", "नाही", "करावे", "शेती", "पिक", "माती", "पाऊस", "खत", "दर"]
HINDI_MARKERS = ["है", "नहीं", "करना", "खेती", "फसल", "मिट्टी", "बारिश", "खाद", "दाम"]

def detect_language_from_text(text: str) -> str:
    """
    Detect the Indian language of input text based on Unicode character distribution
    and localized lexical markers. Defaults to 'hi' if ambiguous Indian script or 'en' for ASCII.
    """
    if not text or not text.strip():
        return "en"

    cleaned = text.strip()

    # Count script characters
    counts: Dict[str, int] = {}
    latin_count = 0
    total_letters = 0

    for ch in cleaned:
        code = ord(ch)
        if (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
            latin_count += 1
            total_letters += 1
            continue

        matched = False
        for start, end, script in UNICODE_SCRIPT_RANGES:
            if start <= code <= end:
                counts[script] = counts.get(script, 0) + 1
                total_letters += 1
                matched = True
                break

    if total_letters == 0:
        return "en"

    # If mostly Latin characters (Hinglish/English)
    if latin_count / total_letters > 0.6:
        text_lower = cleaned.lower()
        tokens = set(re.findall(r'\b[a-z]+\b', text_lower))
        hinglish_words = {
            "kya", "hai", "hain", "khet", "fasal", "gehu", "gehun", "dhan", "sarson",
            "pani", "paani", "barish", "kab", "kare", "karein", "khad", "daale",
            "batao", "bataiye", "salah", "sujhav", "beej", "mandi", "bhav", "daam",
            "mera", "meri", "mere", "aap", "kaise", "kitna", "kitni", "namaste",
            "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "bhi", "nahi"
        }
        if len(tokens & hinglish_words) >= 2 or any(w in tokens for w in ["kya", "khet", "fasal", "khad", "gehu"]):
            return "hi"
        return "en"

    # Find predominant Indic script
    if counts:
        top_script = max(counts, key=counts.get)
        if top_script == "Telugu":
            return "te"
        elif top_script == "Tamil":
            return "ta"
        elif top_script == "Kannada":
            return "kn"
        elif top_script == "Bengali":
            return "bn"
        elif top_script == "Gujarati":
            return "gu"
        elif top_script == "Gurmukhi":
            return "pa"
        elif top_script == "Malayalam":
            return "ml"
        elif top_script == "Odia":
            return "od"
        elif top_script == "Arabic":
            return "ur"
        elif top_script == "Devanagari":
            # Differentiate Hindi vs Marathi using lexical markers
            text_lower = cleaned.lower()
            marathi_score = sum(1 for m in MARATHI_MARKERS if m in text_lower)
            hindi_score = sum(1 for h in HINDI_MARKERS if h in text_lower)
            if marathi_score > hindi_score:
                return "mr"
            return "hi"

    return "hi"

def normalize_language_code(code: Optional[str]) -> str:
    """Normalize language code to supported ISO format."""
    if not code:
        return "hi"
    clean = code.strip().lower()
    if clean.startswith("hi"):
        return "hi"
    elif clean.startswith("te"):
        return "te"
    elif clean.startswith("ta"):
        return "ta"
    elif clean.startswith("kn"):
        return "kn"
    elif clean.startswith("bn"):
        return "bn"
    elif clean.startswith("mr"):
        return "mr"
    elif clean.startswith("gu"):
        return "gu"
    elif clean.startswith("pa"):
        return "pa"
    elif clean.startswith("ml"):
        return "ml"
    elif clean.startswith("od") or clean.startswith("or"):
        return "od"
    elif clean.startswith("ur"):
        return "ur"
    elif clean.startswith("en"):
        return "en"
    return "hi"

def resolve_spoken_language(message: str, spoken_hint: Optional[str] = None) -> str:
    """
    Determine the actual language being spoken/typed by the farmer.
    Requirement: Chat and all generated agronomic advice must strictly follow
    the language being spoken, independent of the UI language.
    Keeps and maintains the established spoken language across multi-turn conversations.
    """
    if not message or not message.strip():
        return normalize_language_code(spoken_hint) or "hi"

    detected = detect_language_from_text(message)

    # If an Indic script was identified, always respect that script
    if detected != "en":
        return detected

    # Text is in Latin alphabet (English, romanized Indic, or short keyword query)
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', message.lower()))

    # Check for romanized Indic / Hinglish markers
    hinglish_markers = {
        "kya", "hai", "hain", "khet", "fasal", "gehu", "gehun", "dhan", "sarson",
        "pani", "paani", "barish", "kab", "kare", "karein", "khad", "daale",
        "batao", "bataiye", "salah", "sujhav", "beej", "bhav", "daam",
        "mera", "meri", "mere", "aap", "kaise", "kitna", "kitni", "namaste",
        "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "bhi", "nahi"
    }
    if tokens & hinglish_markers:
        return "hi"

    # Distinct grammatical words indicating actual English sentence construction
    english_grammar_words = {
        "what", "when", "why", "where", "how", "which", "who", "whom",
        "can", "could", "should", "would", "will", "shall", "must",
        "is", "are", "was", "were", "am", "do", "does", "did",
        "please", "tell", "explain", "give", "suggest", "recommend",
        "about", "with", "from", "into", "because", "have", "has", "had"
    }
    grammar_matches = tokens & english_grammar_words

    # Full English sentence structure (e.g. "what should I plant", "tell me about rainfall")
    if len(grammar_matches) >= 2 or (len(grammar_matches) >= 1 and len(tokens) >= 4):
        return "en"

    # If a non-English language was already established in the conversation, KEEP IT!
    # Short loanwords (e.g., 'weather', 'mandi', 'urea', '10 acres') do not break language continuity.
    if spoken_hint and spoken_hint != "en":
        return normalize_language_code(spoken_hint)

    if len(grammar_matches) >= 1:
        return "en"

    return normalize_language_code(spoken_hint) if spoken_hint else "en"
