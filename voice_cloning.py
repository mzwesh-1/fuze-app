"""
voice_cloning.py — Voice cloning via ElevenLabs API.

Users record a 1-minute voice sample, we upload it to ElevenLabs,
and get back a cloned voice ID that sounds like them.

Setup:
    setx CMT_ELEVENLABS_KEY "your-elevenlabs-api-key"

Get a free key at: https://elevenlabs.io/ (free tier: 10,000 chars/month)
"""

import os
import requests
import tempfile

ELEVENLABS_API = "https://api.elevenlabs.io/v1"


def _get_key():
    key = os.environ.get("CMT_ELEVENLABS_KEY")
    if not key:
        raise EnvironmentError(
            "No ElevenLabs key. Set CMT_ELEVENLABS_KEY.\n"
            "Get a free key at https://elevenlabs.io/"
        )
    return key


def clone_voice(name: str, audio_bytes: bytes, description: str = "CMT SA cloned voice") -> str:
    """
    Clone a voice from recorded audio.

    Args:
        name:        Display name for the cloned voice.
        audio_bytes: WAV/MP3 audio bytes (at least 30 seconds recommended).
        description: Optional description.

    Returns:
        The ElevenLabs voice_id for the cloned voice.
    """
    key = _get_key()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            resp = requests.post(
                f"{ELEVENLABS_API}/voices/add",
                headers={"xi-api-key": key},
                data={"name": name, "description": description},
                files={"files": (f"voice_{name}.wav", f, "audio/wav")},
                timeout=60,
            )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Voice cloning failed: {resp.status_code} {resp.text}")

        return resp.json()["voice_id"]
    finally:
        os.unlink(tmp_path)


def speak_with_clone(text: str, voice_id: str, save_to: str = None) -> bytes:
    """
    Generate speech using a cloned voice.

    Args:
        text:     Text to speak.
        voice_id: ElevenLabs voice_id from clone_voice().
        save_to:  Optional file path to save the audio.

    Returns:
        Audio bytes (MP3).
    """
    key = _get_key()

    resp = requests.post(
        f"{ELEVENLABS_API}/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.5,
                "use_speaker_boost": True,
            },
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"TTS with cloned voice failed: {resp.status_code} {resp.text}")

    audio_bytes = resp.content

    if save_to:
        with open(save_to, "wb") as f:
            f.write(audio_bytes)

    return audio_bytes


def list_cloned_voices() -> list:
    """List all cloned voices on the account."""
    key = _get_key()
    resp = requests.get(
        f"{ELEVENLABS_API}/voices",
        headers={"xi-api-key": key},
        timeout=15,
    )
    if resp.status_code != 200:
        return []

    voices = resp.json().get("voices", [])
    return [{"voice_id": v["voice_id"], "name": v["name"]}
            for v in voices if v.get("category") == "cloned"]


def delete_cloned_voice(voice_id: str):
    """Delete a cloned voice."""
    key = _get_key()
    requests.delete(
        f"{ELEVENLABS_API}/voices/{voice_id}",
        headers={"xi-api-key": key},
        timeout=15,
    )
