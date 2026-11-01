from app.services.language import detect_language_from_text, normalize_language_code, resolve_spoken_language

def test_hindi_detection():
    text = "मेरी मिट्टी में कौन सी फसल उगानी चाहिए?"
    assert detect_language_from_text(text) == "hi"

def test_telugu_detection():
    text = "నా నేలలో ఏ పంట వేయాలి?"
    assert detect_language_from_text(text) == "te"

def test_tamil_detection():
    text = "என் நிலத்தில் என்ன பயிர் நட வேண்டும்?"
    assert detect_language_from_text(text) == "ta"

def test_bengali_detection():
    text = "আমার জমিতে কি ফসল লাগানো উচিত?"
    assert detect_language_from_text(text) == "bn"

def test_marathi_detection():
    text = "माझ्या शेतात कोणते पीक लावावे आणि खत काय द्यावे?"
    assert detect_language_from_text(text) == "mr"

def test_gujarati_detection():
    text = "મારી જમીનમાં કયો પાક વાવવો જોઈએ?"
    assert detect_language_from_text(text) == "gu"

def test_punjabi_detection():
    text = "ਮੇਰੀ ਜ਼ਮੀਨ ਵਿੱਚ ਕਿਹੜੀ ਫਸਲ ਬੀਜਣੀ ਚਾਹੀਦੀ ਹੈ?"
    assert detect_language_from_text(text) == "pa"

def test_english_detection():
    text = "What is the best fertilizer for wheat in Jaipur?"
    assert detect_language_from_text(text) == "en"

def test_normalize_language_code():
    assert normalize_language_code("hi-IN") == "hi"
    assert normalize_language_code("te") == "te"
    assert normalize_language_code("TAMIL") == "ta"
    assert normalize_language_code("unknown") == "hi"

def test_resolve_spoken_language_keeps_active_language():
    # If Telugu is established, short agricultural loanwords like 'weather' or 'mandi' keep Telugu
    assert resolve_spoken_language("weather in Jaipur", spoken_hint="te") == "te"
    assert resolve_spoken_language("mandi price", spoken_hint="hi") == "hi"
    assert resolve_spoken_language("5 acres", spoken_hint="mr") == "mr"

def test_resolve_spoken_language_switches_on_full_english():
    # If a full English question is asked, it correctly identifies English
    assert resolve_spoken_language("What can I spray on my crops this week?", spoken_hint="te") == "en"

def test_resolve_spoken_language_detects_hinglish():
    assert resolve_spoken_language("gehu me khad kab dale", spoken_hint="en") == "hi"
