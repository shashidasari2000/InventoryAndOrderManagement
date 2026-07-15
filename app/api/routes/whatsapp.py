from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.config import get_settings
from app.services import whatsapp_service, auth_service, transaction_service, whisper_service
from app.models.user import User, RegistrationStep
from app.models.message import MessageType
import structlog

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])

# Tracks users in "awaiting reply" state (in-memory; replace with Redis in production)
_pending_confirmations: dict[str, str] = {}


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """WhatsApp webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    statuses = whatsapp_service.parse_webhook_statuses(payload)
    for status_event in statuses:
        if status_event.get("status") == "failed":
            logger.error("whatsapp_delivery_failed", **status_event)
        else:
            logger.info("whatsapp_delivery_status", **status_event)

    messages = whatsapp_service.parse_webhook_payload(payload)

    for msg in messages:
        phone = "+" + msg["from"].lstrip("+")
        msg_id = msg["message_id"]
        msg_type = msg["type"]

        try:
            await _handle_message(db, phone, msg_id, msg_type, msg)
        except Exception as e:
            logger.error("webhook_message_error", phone=phone, error=str(e))
            await whatsapp_service.send_message(phone, "Sorry, something went wrong. Please try again.")

    return {"status": "ok"}


async def _handle_message(db: Session, phone: str, msg_id: str, msg_type: str, msg: dict):
    user = auth_service.get_or_create_user(db, phone)

    # Registration flow
    if user.registration_step != RegistrationStep.COMPLETED:
        if msg_type == "text":
            text = msg.get("text", "").strip()
            if text.lower() in ("hi", "hello", "start"):
                await whatsapp_service.send_message(phone, whatsapp_service.REGISTRATION_PROMPT)
                return
            # Parse registration details
            details = _parse_registration_text(text)
            if details:
                auth_service.register_user(db, phone, details["business_name"], details.get("gst_number"))
                await whatsapp_service.send_message(
                    phone,
                    f"✅ Welcome *{details['business_name']}*!\n\n"
                    "You're all set. Send me any transaction like:\n"
                    "_'Paid ₹12000 to Ramesh supplier via UPI'_\n\n"
                    "I'll generate the accounting entry for you.",
                )
            else:
                await whatsapp_service.send_message(phone, whatsapp_service.REGISTRATION_PROMPT)
        return

    # Check if user is replying to a confirmation
    if phone in _pending_confirmations:
        txn_id = _pending_confirmations[phone]
        if msg_type == "text":
            reply = msg.get("text", "").strip()
            await _handle_confirmation_reply(db, user, phone, txn_id, reply)
        return

    # Process new transaction message
    raw_text = None
    media_id = None
    message_type = MessageType.TEXT

    if msg_type == "text":
        raw_text = msg.get("text", "").strip()
    elif msg_type == "audio":
        media_id = msg.get("audio_id")
        message_type = MessageType.VOICE

    if msg_type == "audio" and media_id:
        try:
            audio_bytes, mime = await whisper_service.download_whatsapp_audio(media_id)
            ext = ".ogg" if "ogg" in mime else ".mp4"
            raw_text = whisper_service.transcribe_audio(audio_bytes, f"audio{ext}")
            await whatsapp_service.send_message(phone, f"🎙️ I heard: _{raw_text}_")
        except Exception as e:
            logger.error("voice_processing_error", error=str(e))
            await whatsapp_service.send_message(phone, "Sorry, I couldn't process your voice message. Please try again.")
            return

    if not raw_text:
        await whatsapp_service.send_message(
            phone, "Please send a text or voice message describing a transaction."
        )
        return

    # Check if this is a query (question about accounts) vs a new transaction
    if _is_query(raw_text):
        reply = _handle_query(db, user, raw_text)
        await whatsapp_service.send_message(phone, reply)
        return

    try:
        txn = transaction_service.create_pending_transaction(
            db, user.id, raw_text, message_type, whatsapp_message_id=msg_id
        )
    except ValueError as e:
        await whatsapp_service.send_message(phone, f"⚠️ {str(e)}\nPlease mention the amount clearly.")
        return

    entry = txn.ledger_entries[0] if txn.ledger_entries else None
    if entry:
        _pending_confirmations[phone] = str(txn.id)
        await whatsapp_service.send_confirmation_message(
            phone,
            narration=txn.narration or raw_text,
            debit_account=entry.debit_account,
            credit_account=entry.credit_account,
            amount=float(txn.amount),
        )
    else:
        await whatsapp_service.send_message(phone, "Entry created but no ledger data found.")


async def _handle_confirmation_reply(
    db: Session, user: User, phone: str, txn_id: str, reply: str
):
    from uuid import UUID
    action_map = {"1": "confirm", "2": "reject"}
    action = action_map.get(reply.strip())

    if action:
        try:
            txn = transaction_service.confirm_transaction(
                db, UUID(txn_id), user.id, action
            )
            del _pending_confirmations[phone]
            if action == "confirm":
                await whatsapp_service.send_message(phone, "✅ Entry confirmed and saved!")
            else:
                await whatsapp_service.send_message(phone, "❌ Entry rejected.")
        except Exception as e:
            await whatsapp_service.send_message(phone, f"Error: {str(e)}")
    elif reply.strip() == "3":
        # Delete the pending transaction and let user resend corrected description
        try:
            from uuid import UUID
            txn = transaction_service.delete_transaction(db, UUID(txn_id), user.id)
            del _pending_confirmations[phone]
            await whatsapp_service.send_message(
                phone,
                "✏️ Entry cancelled. Send the corrected description now:\n"
                "Example: 'Paid ₹5000 to Ram by UPI'\n\n"
                "Or type 'cancel' to stop."
            )
        except Exception as e:
            await whatsapp_service.send_message(phone, f"Error: {str(e)}")
    else:
        await whatsapp_service.send_message(phone, "Reply *1* to Confirm, *2* to Reject, *3* to Edit.")


def _is_query(text: str) -> bool:
    """Detect if the message is a question about accounts rather than a new transaction."""
    t = text.lower().strip()
    query_keywords = [
        "total", "how much", "what is", "what are", "show me", "tell me",
        "balance", "expenses", "income", "summary", "report", "kitna",
        "kitne", "batao", "bata", "kya hai", "how many", "pending",
        "transactions", "this month", "today", "last month",
    ]
    question_starters = ["what", "how", "show", "tell", "give", "list", "kya", "kitna", "kitne"]
    if t.endswith("?"):
        return True
    if any(t.startswith(w) for w in question_starters):
        return True
    if sum(1 for kw in query_keywords if kw in t) >= 2:
        return True
    return False


def _handle_query(db, user, text: str) -> str:
    """Answer natural language queries about the user's accounts."""
    from decimal import Decimal
    t = text.lower()
    summary = transaction_service.get_dashboard_summary(db, user.id)

    def fmt(val) -> str:
        return f"₹{float(val):,.2f}"

    # List all individual expenses with dates (supports date filtering)
    if any(w in t for w in ["list expenses", "list all expenses", "show expenses", "expense details", "expense list", "all expenses", "my expenses", "expenses from"]):
        from_date = _parse_date_from_text(t)
        expenses = transaction_service.list_expenses(db, user.id, from_date=from_date, limit=20)
        if not expenses:
            date_msg = f" from {from_date.strftime('%d %b %Y')}" if from_date else ""
            return f"💸 *No expenses found{date_msg}*\n\nYou haven't recorded any expenses yet."
        lines = ["💸 *Your Expenses*\n"]
        if from_date:
            lines.append(f"_From {from_date.strftime('%d %b %Y')}_\n")
        for exp in expenses:
            date_str = exp['created_at'].strftime("%d %b %Y") if exp['created_at'] else "—"
            lines.append(f"• {date_str}: {exp['narration']} — ₹{exp['amount']:,.0f}")
        total = sum(e['amount'] for e in expenses)
        lines.append(f"\n_Total: ₹{total:,.2f}_")
        return "\n".join(lines)

    # Total expenses (summary only)
    if any(w in t for w in ["expense", "kharch", "payment", "paid total", "total paid"]):
        return (
            f"💸 *Total Expenses*\n\n"
            f"{fmt(summary['total_expenses'])}\n\n"
            f"_(confirmed entries only)_"
        )

    # List all individual incomes with dates (supports date filtering)
    if any(w in t for w in ["list income", "list all income", "show income", "income details", "income list", "all income", "my income", "income from"]):
        from_date = _parse_date_from_text(t)
        incomes = transaction_service.list_incomes(db, user.id, from_date=from_date, limit=20)
        if not incomes:
            date_msg = f" from {from_date.strftime('%d %b %Y')}" if from_date else ""
            return f"💰 *No income found{date_msg}*\n\nYou haven't recorded any income yet."
        lines = ["💰 *Your Income*\n"]
        if from_date:
            lines.append(f"_From {from_date.strftime('%d %b %Y')}_\n")
        for inc in incomes:
            date_str = inc['created_at'].strftime("%d %b %Y") if inc['created_at'] else "—"
            lines.append(f"• {date_str}: {inc['narration']} — ₹{inc['amount']:,.0f}")
        total = sum(i['amount'] for i in incomes)
        lines.append(f"\n_Total: ₹{total:,.2f}_")
        return "\n".join(lines)

    # Total income (summary only)
    if any(w in t for w in ["total income", "received total", "total received", "earnings"]):
        return (
            f"💰 *Total Income*\n\n"
            f"{fmt(summary['total_income'])}\n\n"
            f"_(confirmed entries only)_"
        )

    # Receivables
    if any(w in t for w in ["receivable", "due from", "customer due", "paana"]):
        return (
            f"📥 *Total Receivables*\n\n"
            f"{fmt(summary['total_receivables'])}\n\n"
            f"_(amount due from customers)_"
        )

    # Payables
    if any(w in t for w in ["payable", "due to", "supplier due", "dena"]):
        return (
            f"📤 *Total Payables*\n\n"
            f"{fmt(summary['total_payables'])}\n\n"
            f"_(amount due to suppliers)_"
        )

    # Pending confirmations
    if any(w in t for w in ["pending", "confirm", "unconfirmed"]):
        return (
            f"⏳ *Pending Entries*\n\n"
            f"{summary['pending_confirmations']} transaction(s) waiting for your confirmation.\n\n"
            f"Open the dashboard to review: http://localhost:3000/dashboard/transactions"
        )

    # Full summary (default for generic questions)
    profit = float(summary['total_income']) - float(summary['total_expenses'])
    profit_label = "Profit" if profit >= 0 else "Loss"
    return (
        f"📊 *Account Summary*\n\n"
        f"💰 Income: {fmt(summary['total_income'])}\n"
        f"💸 Expenses: {fmt(summary['total_expenses'])}\n"
        f"📈 Net {profit_label}: ₹{abs(profit):,.2f}\n\n"
        f"📥 Receivables: {fmt(summary['total_receivables'])}\n"
        f"📤 Payables: {fmt(summary['total_payables'])}\n\n"
        f"✅ Confirmed entries: {summary['total_transactions']}\n"
        f"⏳ Pending: {summary['pending_confirmations']}"
    )


def _parse_date_from_text(text: str) -> datetime | None:
    """Extract date from natural language queries like 'from 18th June', 'from 1-1-2026'."""
    import re
    from dateutil import parser

    text_lower = text.lower()
    current_year = datetime.now().year

    # Extract date part after "from"
    match = re.search(r'from\s+(.+?)(?:\s+till|\s+to|\s+until|$)', text_lower)
    if not match:
        return None

    date_str = match.group(1).strip()

    # Replace ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

    # Common format fixes
    date_str = date_str.replace('-', ' ').replace('/', ' ')

    try:
        # Use dateutil parser with fuzzy matching
        parsed = parser.parse(date_str, fuzzy=True, default=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
        # If no year was specified, parser might use 1900 - fix to current year
        if parsed.year < 2000:
            parsed = parsed.replace(year=current_year)
        return parsed
    except (ValueError, TypeError):
        pass

    return None


def _parse_registration_text(text: str) -> dict | None:
    """Parse registration details from text like 'Business Name: ABC\nGST: 123'."""
    import re
    lines = text.strip().split("\n")
    data = {}
    for line in lines:
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            val = val.strip()
            if key in ("business_name", "business", "name"):
                data["business_name"] = val
            elif key in ("gst", "gst_number", "gstin"):
                data["gst_number"] = val
    return data if "business_name" in data else None
