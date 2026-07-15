"""
Voice-to-text service.
Priority: Sarvam AI (Indian languages) → Groq Whisper (free) → OpenAI Whisper.
"""
import os
import tempfile
import httpx
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

SUPPORTED_LANGUAGES = ["en", "hi", "te"]


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe audio bytes.
    Priority: Sarvam AI → Groq → OpenAI.
    Returns English text suitable for the AI accounting parser.
    """
    suffix = os.path.splitext(filename)[1] or ".webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        if settings.SARVAM_API_KEY:
            return _transcribe_sarvam(tmp_path, filename)
        elif settings.GROQ_API_KEY:
            return _transcribe_groq(tmp_path, filename)
        elif settings.OPENAI_API_KEY:
            return _transcribe_openai(tmp_path)
        else:
            raise RuntimeError(
                "No transcription API key configured. "
                "Set SARVAM_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY in .env"
            )
    finally:
        os.unlink(tmp_path)


def _transcribe_sarvam(tmp_path: str, filename: str) -> str:
    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY)
    with open(tmp_path, "rb") as f:
        response = client.speech_to_text.transcribe(
            file=f,
            model="saaras:v3",
            mode="translate",
        )
    transcript = response.transcript or ""
    logger.info("sarvam_transcription_success", length=len(transcript))
    return transcript.strip()


def _transcribe_groq(tmp_path: str, filename: str) -> str:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    with open(tmp_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=(filename, f),
            response_format="text",
            language="en",
        )
    logger.info("groq_whisper_success", length=len(str(transcript)))
    return str(transcript).strip()


def _transcribe_openai(tmp_path: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    with open(tmp_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=audio_file,
            response_format="text",
        )
    logger.info("openai_whisper_success", length=len(str(transcript)))
    return str(transcript).strip()


async def download_whatsapp_audio(media_id: str) -> tuple[bytes, str]:
    """
    Download audio file from WhatsApp Cloud API by media_id.
    Returns (audio_bytes, mime_type).
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        # Step 1: Get media URL
        url_resp = await client.get(
            f"{settings.WHATSAPP_API_URL}/{media_id}",
            headers=headers,
        )
        url_resp.raise_for_status()
        media_data = url_resp.json()
        media_url = media_data["url"]
        mime_type = media_data.get("mime_type", "audio/ogg")

        # Step 2: Download the file
        file_resp = await client.get(media_url, headers=headers)
        file_resp.raise_for_status()

    logger.info("whatsapp_audio_downloaded", media_id=media_id, size=len(file_resp.content))
    return file_resp.content, mime_type
