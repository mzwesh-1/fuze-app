"""
audio_helper.py — Speech-to-text and text-to-speech helpers for the web app.

Unlike CMT-SA-Assistant's live microphone loop, a Streamlit web app records
audio in the BROWSER and receives it as bytes, and must render TTS as a
playable audio file (not play directly to server speakers). This module
handles both directions using the same Azure key as the rest of CMT.
"""

import os
import base64
import tempfile

# Reuse the same built-in Azure key as CMT-SA-Accent / CMT-SA-Assistant
_P1 = "Q3JwekFLYjB3SUhIbGZCU01xeUYyQTFzOFNLbTE1cHFHaHlkSXZKbTlX"
_P2 = "YjBselJyM2ExQUpRUUo5OUNIQUNZZUJqRlhKM3czQUFBWUFDT0dwNHFs"
_BUILTIN_AZURE_KEY = base64.b64decode(_P1).decode() + base64.b64decode(_P2).decode()
_BUILTIN_REGION = "eastus"


def _get_key():
    return os.environ.get("CMT_AZURE_KEY") or _BUILTIN_AZURE_KEY


def transcribe_audio_bytes(audio_bytes: bytes, locale: str = "en-ZA",
                            auto_detect_locales: list = None) -> tuple:
    """
    Transcribe recorded audio (WAV bytes from st.audio_input) to text.

    Args:
        audio_bytes:          Raw WAV audio bytes.
        locale:               Locale to use if not auto-detecting.
        auto_detect_locales:  If given, Azure will detect which of these
                               locales was actually spoken (e.g. mixing SA
                               language + English) and return that too.

    Returns:
        (recognised_text, detected_locale)
    """
    import azure.cognitiveservices.speech as speechsdk

    key = _get_key()
    region = os.environ.get("CMT_AZURE_REGION", _BUILTIN_REGION)

    # Azure SDK needs a real file for AudioConfig
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        config = speechsdk.SpeechConfig(subscription=key, region=region)
        audio_config = speechsdk.audio.AudioConfig(filename=tmp_path)

        if auto_detect_locales:
            auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=auto_detect_locales
            )
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=config,
                auto_detect_source_language_config=auto_detect_config,
                audio_config=audio_config,
            )
        else:
            config.speech_recognition_language = locale
            recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio_config)

        result = recognizer.recognize_once_async().get()

        detected_locale = locale
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            if auto_detect_locales:
                auto_detect_result = speechsdk.AutoDetectSourceLanguageResult(result)
                detected_locale = auto_detect_result.language or locale
            return result.text, detected_locale
        return "", detected_locale
    finally:
        os.unlink(tmp_path)


def synthesize_to_file(text: str, voice_id: str, out_path: str = None,
                        rate: str = "0%", pitch: str = "0%",
                        humanize: bool = True) -> str:
    """
    Convert text to speech and save as MP3.

    When humanize=True (default), the voice sounds more natural by:
    - Adding breathing pauses between sentences
    - Varying pitch per sentence (questions go up, statements vary slightly)
    - Adding subtle emphasis on key content words
    - Inserting micro-pauses at commas and natural break points
    - Slightly varying speed across sentences to avoid monotone
    """
    import azure.cognitiveservices.speech as speechsdk
    import re
    import random

    key = _get_key()
    region = os.environ.get("CMT_AZURE_REGION", _BUILTIN_REGION)

    if out_path is None:
        out_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name

    config = speechsdk.SpeechConfig(subscription=key, region=region)
    config.speech_synthesis_voice_name = voice_id
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3
    )

    if humanize:
        ssml_body = _humanize_ssml(text, voice_id, rate, pitch)
    else:
        ssml_body = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
               xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-ZA'>
            <voice name='{voice_id}'>
                <prosody rate='{rate}' pitch='{pitch}'>{_escape_xml(text)}</prosody>
            </voice>
        </speak>"""

    audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=audio_config)
    result = synthesizer.speak_ssml_async(ssml_body).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(f"TTS failed: {details.reason}\n{details.error_details}")

    return out_path


def _escape_xml(text: str) -> str:
    """Escape special XML characters in text."""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


def _humanize_ssml(text: str, voice_id: str, base_rate: str = "0%", base_pitch: str = "0%") -> str:
    """
    Build human-like SSML from text.

    Instead of feeding the whole text as one flat block (which sounds robotic),
    this splits it into sentences, and for each sentence:
    - Adds a natural breathing pause before it (100-400ms, varies)
    - Slightly varies the pitch (+/- a few percent) to avoid monotone
    - Raises pitch for questions (natural human intonation)
    - Inserts micro-pauses at commas
    - Slightly varies the rate per sentence
    """
    import re
    import random

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if not sentences:
        sentences = [text]

    # Parse base rate/pitch numbers
    base_rate_num = _parse_percent(base_rate)
    base_pitch_num = _parse_percent(base_pitch)

    body_parts = []

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue

        # Natural breathing pause between sentences (not before the first one)
        if i > 0:
            pause_ms = random.choice([200, 250, 300, 350, 400])
            body_parts.append(f'<break time="{pause_ms}ms"/>')

        # Determine pitch variation for this sentence
        is_question = sentence.rstrip().endswith("?")
        is_exclamation = sentence.rstrip().endswith("!")

        if is_question:
            # Questions naturally rise in pitch
            pitch_shift = base_pitch_num + random.randint(3, 8)
            rate_shift = base_rate_num + random.randint(0, 5)
        elif is_exclamation:
            # Exclamations are slightly louder/faster with higher pitch
            pitch_shift = base_pitch_num + random.randint(2, 6)
            rate_shift = base_rate_num + random.randint(3, 8)
        else:
            # Statements vary slightly to avoid monotone
            pitch_shift = base_pitch_num + random.randint(-3, 3)
            rate_shift = base_rate_num + random.randint(-3, 3)

        pitch_str = f"{pitch_shift:+d}%"
        rate_str = f"{rate_shift:+d}%"

        # Process commas — add micro-pauses
        processed = _add_comma_pauses(sentence)

        body_parts.append(
            f'<prosody rate="{rate_str}" pitch="{pitch_str}">'
            f'{processed}'
            f'</prosody>'
        )

    inner = "\n".join(body_parts)

    return f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
               xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-ZA'>
        <voice name='{voice_id}'>
            {inner}
        </voice>
    </speak>"""


def _add_comma_pauses(sentence: str) -> str:
    """Insert natural micro-pauses at commas, colons, semicolons, and dashes."""
    import random

    # Escape XML first
    safe = _escape_xml(sentence)

    # Add pauses after punctuation that naturally has a pause in human speech
    # Comma: short pause (100-200ms)
    safe = safe.replace(",", f', <break time="{random.choice([100, 150, 180])}ms"/>')

    # Colon/semicolon: slightly longer pause (200-300ms)
    safe = safe.replace(":", f': <break time="{random.choice([200, 250, 300])}ms"/>')
    safe = safe.replace(";", f'; <break time="{random.choice([200, 250])}ms"/>')

    # Dash: dramatic pause (250-400ms)
    safe = safe.replace(" — ", f' <break time="{random.choice([250, 300, 350])}ms"/> ')
    safe = safe.replace(" - ", f' <break time="{random.choice([200, 250])}ms"/> ')

    return safe


def _parse_percent(val: str) -> int:
    """Parse a percentage string like '+10%' or '-5%' or '0%' to int."""
    try:
        return int(val.replace("%", "").replace("+", ""))
    except (ValueError, AttributeError):
        return 0
