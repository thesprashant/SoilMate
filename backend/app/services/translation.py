import asyncio
import logging
import re
from typing import Optional
import httpx
from deep_translator import GoogleTranslator
from app.config import settings
from app.services.language import normalize_language_code

logger = logging.getLogger(__name__)

# Mapping from ISO code to deep_translator language names
DEEP_TRANSLATE_LANG_MAP = {
    "hi": "hindi",
    "te": "telugu",
    "ta": "tamil",
    "kn": "kannada",
    "bn": "bengali",
    "mr": "marathi",
    "gu": "gujarati",
    "pa": "punjabi",
    "ml": "malayalam",
    "od": "odia",
    "ur": "urdu",
    "en": "english"
}

# Mapping to Sarvam AI language codes
SARVAM_LANG_MAP = {
    "hi": "hi-IN",
    "te": "te-IN",
    "ta": "ta-IN",
    "kn": "kn-IN",
    "bn": "bn-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
    "ml": "ml-IN",
    "od": "or-IN",
    "or": "or-IN",
    "en": "en-IN"
}

def align_grammatical_gender(text: str, target_lang: str = "hi", gender: str = "female") -> str:
    """
    Ensure grammatical gender consistency for first-person self-references (the agent).
    When speaking with a female voice (Priya), converts masculine self-referencing verbal
    inflections and titles into their feminine counterparts in Hindi, Punjabi, Marathi, etc.
    Does NOT alter 2nd person respectful advice given to the farmer (e.g. 'आप कर सकते हैं').
    """
    if not text or not text.strip():
        return text

    target_lang = normalize_language_code(target_lang)
    if gender.lower() != "female":
        return text

    if target_lang == "hi":
        # 1. First-person habit/present tense: "करता हूँ" -> "करती हूँ", "बताता हूँ" -> "बताती हूँ"
        # Since 'हूँ' / 'हु' only ever accompanies 'मैं' (1st person), (\w+)ता before हूँ/हु is 100% 1st person masculine!
        text = re.sub(r'([\u0904-\u0954]+)ता\s+(हूँ|हु|हू)(?![\u0900-\u0954])', r'\1ती \2', text)

        # 2. First-person continuous: "कर रहा हूँ" -> "कर रही हूँ", "बता रहा हूँ" -> "बता रही हूँ"
        text = re.sub(r'(?<![\u0900-\u0954])रहा\s+(हूँ|हु|हू)(?![\u0900-\u0954])', r'रही \1', text)

        # 3. First-person future tense:
        # e.g. करूँगा, करूंगा, बताऊँगा, बताऊंगा, जाऊँगा, देखूँगा, दूँगा, लूँगा, रहूँगा, लाऊँगा, भेजूँगा
        text = re.sub(r'([\u0904-\u0954]+[\u0942\u090A\u0909][\u0901\u0902]?)गा(?![\u0900-\u0954])', r'\1गी', text)
        text = re.sub(r'([\u0904-\u0954]+)ऊंगा(?![\u0900-\u0954])', r'\1ऊंगी', text)

        # Specific 1st-person future monosyllabic verbs
        text = re.sub(r'(?<![\u0900-\u0954])दूँगा(?![\u0900-\u0954])', 'दूँगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])दूंगा(?![\u0900-\u0954])', 'दूंगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])लूँगा(?![\u0900-\u0954])', 'लूँगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])लूंगा(?![\u0900-\u0954])', 'लूंगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])हूँगा(?![\u0900-\u0954])', 'हूँगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])हूंगा(?![\u0900-\u0954])', 'हूंगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])होऊँगा(?![\u0900-\u0954])', 'होऊँगी', text)
        text = re.sub(r'(?<![\u0900-\u0954])होऊंगा(?![\u0900-\u0954])', 'होऊंगी', text)

        # 4. First-person past participle: "गया हूँ" -> "गई हूँ", "आया हूँ" -> "आई हूँ"
        text = re.sub(r'(?<![\u0900-\u0954])गया\s+(हूँ|हु|हू)(?![\u0900-\u0954])', r'गई \1', text)
        text = re.sub(r'(?<![\u0900-\u0954])आया\s+(हूँ|हु|हू)(?![\u0900-\u0954])', r'आई \1', text)
        text = re.sub(r'(?<![\u0900-\u0954])(पहुंचा|पहुँचा)\s+(हूँ|हु|हू)(?![\u0900-\u0954])', r'पहुंची \2', text)

        # 5. Self-referential titles & possessives:
        # "मैं आपका कृषि सलाहकार हूँ" -> "मैं आपकी कृषि सलाहकार हूँ"
        # "आपका कृषि मित्र" -> "आपकी कृषि सखी"
        # "आपका सहायक" -> "आपकी सहायिका"
        text = re.sub(
            r'(?<![\u0900-\u0954])आपका\s+(कृषि\s+सलाहकार|सलाहकार|कृषि\s+मित्र|सहायक|एआई\s+सहायक|साथी|दोस्त|मित्र)(?![\u0900-\u0954])',
            lambda m: (
                'आपकी कृषि सखी' if 'मित्र' in m.group(0)
                else 'आपकी सहायिका' if 'सहायक' in m.group(0)
                else f'आपकी {m.group(1)}'
            ),
            text
        )
        text = re.sub(r'(?<![\u0900-\u0954])मैं\s+आपका(?!\s+(खेत|खलिहान|गाँव|घर|फसल|उत्पाद|जमीन))', 'मैं आपकी', text)
        text = re.sub(r'(?<![\u0900-\u0954])(मेरा)\s+(सुझाव|सलाह)(?![\u0900-\u0954])', r'मेरी \2', text)
        text = re.sub(r'सलाहकार\s+होने\s+के\s+नाते,\s+मैं', 'कृषि सखी होने के नाते, मैं', text)

        # 6. Romanized / Hinglish variants (if any):
        text = re.sub(r'(\b[a-zA-Z]+)ta\s+(hu|hoon)\b', r'\1ti \2', text, flags=re.IGNORECASE)
        text = re.sub(r'\braha\s+(hu|hoon)\b', r'rahi \1', text, flags=re.IGNORECASE)
        text = re.sub(r'(\b[a-zA-Z]+)unga\b', r'\1ungi', text, flags=re.IGNORECASE)
        text = re.sub(r'\baapka\s+(salahkar|krishi\s+salahkar|sahayak|mitra|saathi|dost)\b', r'aapki \1', text, flags=re.IGNORECASE)

    elif target_lang == "pa":  # Punjabi
        text = re.sub(r'(\b[\u0A00-\u0A7F]+)ਦਾ\s+ਹਾਂ\b', r'\1ਦੀ ਹਾਂ', text)
        text = re.sub(r'\bਰਿਹਾ\s+ਹਾਂ\b', 'ਰਹੀ ਹਾਂ', text)
        text = re.sub(r'(\b[\u0A00-\u0A7F]+)ਾਂਗਾ\b', r'\1ਾਂਗੀ', text)
        text = re.sub(r'\bਤੁਹਾਡਾ\s+ਸਲਾਹਕਾਰ\b', 'ਤੁਹਾਡੀ ਸਲਾਹਕਾਰ', text)

    elif target_lang == "mr":  # Marathi
        text = re.sub(r'(\b[\u0900-\u097F]+)तो\s+आहे\b', r'\1ते आहे', text)
        text = re.sub(r'\bतुमचा\s+सल्लागार\b', 'तुमची सल्लागार', text)

    return text

async def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text between English and Indian languages.
    Tries Sarvam Mayura API first if key configured; falls back to deep-translator.
    """
    s_lang = normalize_language_code(source_lang)
    t_lang = normalize_language_code(target_lang)

    if not text or not text.strip():
        return ""
    if s_lang == t_lang:
        return text

    # Attempt Sarvam AI translation if key present
    sarvam_key = settings.sarvam_api_key.strip()
    if sarvam_key:
        try:
            s_code = SARVAM_LANG_MAP.get(s_lang)
            t_code = SARVAM_LANG_MAP.get(t_lang)
            if s_code and t_code:
                url = "https://api.sarvam.ai/translate"
                headers = {
                    "api-subscription-key": sarvam_key,
                    "Content-Type": "application/json"
                }
                payload = {
                    "input": text,
                    "source_language_code": s_code,
                    "target_language_code": t_code,
                    "mode": "formal",
                    "speaker_gender": "Female" if settings.speaker_gender.lower() == "female" else "Male"
                }
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, headers=headers, timeout=8.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        translated = data.get("translated_text")
                        if translated:
                            return translated.strip()
        except Exception as e:
            logger.warning(f"[translate_text] Sarvam AI failed: {e}. Falling back to deep-translator.")

    # Robust fallback: deep-translator
    try:
        s_target = DEEP_TRANSLATE_LANG_MAP.get(s_lang, "auto")
        t_target = DEEP_TRANSLATE_LANG_MAP.get(t_lang, "english")

        loop = asyncio.get_running_loop()
        translated = await asyncio.wait_for(loop.run_in_executor(
            None, lambda: GoogleTranslator(source=s_target, target=t_target).translate(text)
        ), 10)
        if not translated:
            raise ValueError("No translation returned")
        return translated.strip()
    except Exception as e:
        logger.error(f"[translate_text] Deep-translator error: {e}. Returning original text.")
        raise RuntimeError("Translation is temporarily unavailable; please retry or choose another language.") from e

async def translate_to_english(text: str, source_lang: str) -> str:
    """Helper to convert any Indian language text to English for agent processing."""
    if source_lang == "en":
        return text
    return await translate_text(text, source_lang=source_lang, target_lang="en")

async def translate_from_english(text: str, target_lang: str) -> str:
    """Helper to convert agent's English output into the farmer's native language with gender consistency."""
    if not text or not text.strip():
        return ""

    t_code = normalize_language_code(target_lang)
    if t_code == "en":
        return text

    # If response is already predominantly in Devanagari script (e.g. agent answered directly in Hindi)
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if has_devanagari and t_code in ["hi", "mr"]:
        return align_grammatical_gender(text, target_lang=t_code, gender=settings.speaker_gender)

    translated = await translate_text(text, source_lang="en", target_lang=t_code)
    aligned = align_grammatical_gender(translated, target_lang=t_code, gender=settings.speaker_gender)
    return aligned

