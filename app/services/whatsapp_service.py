"""
WhatsApp Cloud API messaging service.
Handles sending messages and parsing incoming webhook payloads.
"""
import httpx
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

REGISTRATION_PROMPT = (
    "Welcome to *AI Accounting Assistant* 🧾\n\n"
    "I help you record accounting entries via WhatsApp.\n\n"
    "Please reply with your details in this format:\n"
    "```\nBusiness Name: Your Business\nGST: XXXXXXXXXXXX (optional)\n```"
)

CONFIRMATION_TEMPLATE = (
    "✅ *Suggested Accounting Entry*\n\n"
    "📌 {narration}\n\n"
    "*{debit_account}* Dr ₹{amount:,.2f}\n"
    "  To *{credit_account}* ₹{amount:,.2f}\n\n"
    "Reply:\n*1* - Confirm ✅\n*2* - Reject ❌\n*3* - Edit ✏️"
)


async def send_message(to: str, text: str) -> bool:
    success, _ = await send_message_result(to, text)
    return success


async def send_message_result(to: str, text: str) -> tuple[bool, str | None]:
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("whatsapp_not_configured")
        return False, "WhatsApp not configured"

    url = f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to.lstrip("+"),
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("whatsapp_send_failed", status=resp.status_code, body=resp.text)
            return False, resp.text

    data = resp.json()
    message_id = None
    if data.get("messages"):
        message_id = data["messages"][0].get("id")
    logger.info("whatsapp_message_sent", to=to, message_id=message_id)
    return True, None


async def send_otp_template(to: str, otp: str) -> tuple[bool, str | None]:
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("whatsapp_not_configured")
        return False, "WhatsApp not configured"
    if not settings.WHATSAPP_OTP_TEMPLATE_NAME:
        return False, "WHATSAPP_OTP_TEMPLATE_NAME is not configured"

    url = f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_OTP_TEMPLATE_NAME,
            "language": {"code": settings.WHATSAPP_OTP_TEMPLATE_LANGUAGE},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": otp}],
                }
            ],
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("whatsapp_otp_template_failed", status=resp.status_code, body=resp.text)
            return False, resp.text

    data = resp.json()
    message_id = None
    if data.get("messages"):
        message_id = data["messages"][0].get("id")
    logger.info("whatsapp_otp_template_sent", to=to, message_id=message_id)
    return True, None


async def send_confirmation_message(
    to: str,
    narration: str,
    debit_account: str,
    credit_account: str,
    amount: float,
) -> bool:
    text = CONFIRMATION_TEMPLATE.format(
        narration=narration,
        debit_account=debit_account,
        credit_account=credit_account,
        amount=amount,
    )
    return await send_message(to, text)


def parse_webhook_payload(payload: dict) -> list[dict]:
    """
    Extract message objects from WhatsApp webhook payload.
    Returns list of dicts with keys: from, message_id, type, text, audio_id.
    """
    messages = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    parsed = {
                        "from": msg.get("from"),
                        "message_id": msg.get("id"),
                        "type": msg.get("type"),
                        "text": None,
                        "audio_id": None,
                    }
                    if msg["type"] == "text":
                        parsed["text"] = msg.get("text", {}).get("body", "")
                    elif msg["type"] == "audio":
                        parsed["audio_id"] = msg.get("audio", {}).get("id")
                    messages.append(parsed)
    except Exception as e:
        logger.error("webhook_parse_error", error=str(e))
    return messages


def parse_webhook_statuses(payload: dict) -> list[dict]:
    statuses = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    errors = status.get("errors") or []
                    statuses.append(
                        {
                            "message_id": status.get("id"),
                            "recipient_id": status.get("recipient_id"),
                            "status": status.get("status"),
                            "timestamp": status.get("timestamp"),
                            "conversation": status.get("conversation"),
                            "pricing": status.get("pricing"),
                            "errors": errors,
                        }
                    )
    except Exception as e:
        logger.error("webhook_status_parse_error", error=str(e))
    return statuses
