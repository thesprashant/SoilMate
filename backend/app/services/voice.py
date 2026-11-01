import base64
import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings
from app.services.language import normalize_language_code, resolve_spoken_language
from app.services.translation import SARVAM_LANG_MAP

logger = logging.getLogger(__name__)

async def speech_to_text(audio_bytes: bytes, filename: str = "audio.wav", language_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Transcribe audio stream into text using Sarvam Saaras v2 STT.
    Returns transcribed text and detected language.
    """
    sarvam_key = settings.sarvam_api_key.strip()
    if not sarvam_key:
        return {
            "text": "",
            "language": language_hint or "hi",
            "error": "SARVAM_API_KEY not configured. Speech-to-text requires Sarvam AI API key."
        }

    # If language_hint is explicitly given, map it; otherwise use "unknown" for auto-detection
    if not language_hint or language_hint in ("auto", "unknown"):
        lang_code = "unknown"
    else:
        lang_code = SARVAM_LANG_MAP.get(normalize_language_code(language_hint), "unknown")

    url = "https://api.sarvam.ai/speech-to-text"
    headers = {
        "api-subscription-key": sarvam_key
    }
    
    files = {
        "file": (filename, audio_bytes, "audio/webm" if filename.endswith(".webm") else "audio/mp4" if filename.endswith(".mp4") else "audio/ogg" if filename.endswith(".ogg") else "audio/wav")
    }
    data = {
        "model": "saaras:v2",
        "language_code": lang_code
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, files=files, data=data, timeout=15.0)
            if resp.status_code == 200:
                result = resp.json()
                transcript = result.get("transcript", "")
                raw_code = result.get("language_code", lang_code)
                detected = raw_code.split("-")[0] if raw_code and raw_code != "unknown" else (language_hint or "hi")
                if transcript:
                    detected = resolve_spoken_language(transcript, spoken_hint=detected)
                return {
                    "text": transcript.strip(),
                    "language": detected,
                    "confidence": result.get("confidence")
                }
            else:
                logger.error(f"[speech_to_text] Sarvam STT returned status {resp.status_code}: {resp.text}")
                return {
                    "text": "",
                    "language": normalize_language_code(language_hint),
                    "error": f"STT failed with HTTP {resp.status_code}"
                }
    except Exception as e:
        logger.error(f"[speech_to_text] Error: {e}")
        return {
            "text": "",
            "language": normalize_language_code(language_hint),
            "error": str(e)
        }

def clean_text_for_speech(text: str) -> str:
    """Prepare text for natural, conversational TTS synthesis without markdown noise."""
    import re
    # Remove markdown headers, bold, italics, code blocks
    cleaned = re.sub(r'[*_#`~]', '', text)
    # Remove bullet markers at line start
    cleaned = re.sub(r'^\s*[-•*]\s+', '', cleaned, flags=re.MULTILINE)
    # Remove numbered list prefixes like "1. ", "2. "
    cleaned = re.sub(r'^\s*\d+\.\s+', '', cleaned, flags=re.MULTILINE)
    # Remove common emojis
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned)
    # Collapse multiple newlines into period pause
    cleaned = re.sub(r'\n+', '. ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # If long, truncate cleanly at sentence boundary (within 450 chars)
    if len(cleaned) > 450:
        truncated = cleaned[:450]
        # Look for last sentence terminator: Devanagari danda (।), period, question mark, exclamation
        last_punct = max(
            truncated.rfind('।'),
            truncated.rfind('.'),
            truncated.rfind('?'),
            truncated.rfind('!')
        )
        if last_punct > 150:
            cleaned = truncated[:last_punct + 1]
        else:
            cleaned = truncated.rsplit(' ', 1)[0] + '।'

    return cleaned

async def text_to_speech(text: str, language: str = "hi") -> Optional[str]:
    """
    Synthesize text into natural voice audio using Sarvam Bulbul v3 TTS.
    Returns base64-encoded WAV audio string.
    """
    sarvam_key = settings.sarvam_api_key.strip()
    if not sarvam_key or not text.strip():
        return None

    lang_iso = normalize_language_code(language)
    lang_code = SARVAM_LANG_MAP.get(lang_iso, "hi-IN")
    
    tts_text = clean_text_for_speech(text)
    if not tts_text:
        return None

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": sarvam_key,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [tts_text],
        "target_language_code": lang_code,
        "speaker": settings.sarvam_speaker,
        "model": "bulbul:v3",
        "pace": 1.0,
        "temperature": 0.6
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                audios = data.get("audios", [])
                if audios and len(audios) > 0:
                    return audios[0] # Already base64 encoded by Sarvam API
            else:
                logger.warning(f"[text_to_speech] Sarvam TTS status {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        logger.error(f"[text_to_speech] TTS error: {e}")

    return None
