import random
import string
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models.user import User, UserRole, RegistrationStep
from app.models.otp import OTPRecord
import structlog

logger = structlog.get_logger()
settings = get_settings()


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()


def verify_otp_hash(otp: str, hashed: str) -> bool:
    return bcrypt.checkpw(otp.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def _twilio_configured() -> bool:
    """Return True only when real (non-placeholder) Twilio credentials are set."""
    sid = settings.TWILIO_ACCOUNT_SID or ""
    token = settings.TWILIO_AUTH_TOKEN or ""
    placeholders = ("your_", "xxxxxxx", "ACxxxxx")
    if not sid or not token:
        return False
    if any(p in sid.lower() for p in placeholders):
        return False
    if any(p in token.lower() for p in placeholders):
        return False
    return True


def _whatsapp_configured() -> bool:
    token = settings.WHATSAPP_ACCESS_TOKEN or ""
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
    placeholders = ("your_", "xxxxxxx", "phone_number_id")
    if not token or not phone_id:
        return False
    if any(p in token.lower() for p in placeholders):
        return False
    if any(p in phone_id.lower() for p in placeholders):
        return False
    return True


def _send_otp_whatsapp(phone_number: str, otp: str) -> tuple[bool, str | None]:
    """Send OTP using WhatsApp Cloud API. Template is preferred for login OTP."""
    import asyncio
    from app.services.whatsapp_service import send_message_result, send_otp_template

    if not _whatsapp_configured():
        return False, "WhatsApp not configured"

    if settings.WHATSAPP_OTP_TEMPLATE_NAME:
        return asyncio.run(send_otp_template(phone_number, otp))

    msg = (
        f"🔐 *AI Accounting Assistant*\n\n"
        f"Your OTP is: *{otp}*\n"
        f"Valid for {settings.OTP_EXPIRE_MINUTES} minutes.\n\n"
        f"Do not share this with anyone."
    )
    return asyncio.run(send_message_result(phone_number, msg))


def send_otp(phone_number: str, otp: str) -> tuple[bool, str | None]:
    """Send OTP via WhatsApp and/or Twilio. Falls back to logging in dev mode."""
    # Always print to terminal (dev convenience)
    print(f"\n{'='*50}\nOTP for {phone_number}: {otp}\n{'='*50}\n")
    logger.warning("otp_generated", phone=phone_number, otp=otp)

    # Skip real delivery when using a fixed default OTP (mobile / tablet convenience)
    if settings.USE_DEFAULT_OTP:
        logger.info("otp_default_mode", phone=phone_number, otp=settings.DEFAULT_OTP)
        return True, None

    whatsapp_sent = False
    whatsapp_error = None
    if _whatsapp_configured():
        try:
            whatsapp_sent, whatsapp_error = _send_otp_whatsapp(phone_number, otp)
            if whatsapp_sent:
                logger.info("otp_sent_whatsapp", phone=phone_number)
            else:
                logger.warning("whatsapp_otp_send_failed", phone=phone_number, error=whatsapp_error)
        except Exception as e:
            whatsapp_error = str(e)
            logger.warning("whatsapp_otp_send_failed", phone=phone_number, error=whatsapp_error)

    # Try Twilio SMS if configured
    if _twilio_configured():
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=f"Your AI Accounting Assistant OTP is: {otp}. Valid for {settings.OTP_EXPIRE_MINUTES} minutes.",
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number,
            )
            logger.info("otp_sent_twilio", phone=phone_number)
            return True, None
        except Exception as e:
            logger.error("twilio_send_failed", error=str(e))
            return False, str(e)

    if whatsapp_sent:
        return True, None

    if _whatsapp_configured() and not settings.WHATSAPP_OTP_TEMPLATE_NAME:
        return (
            False,
            "WhatsApp OTP failed. Business-initiated OTP messages usually require an approved template. "
            "Set WHATSAPP_OTP_TEMPLATE_NAME and WHATSAPP_OTP_TEMPLATE_LANGUAGE. "
            f"Provider error: {whatsapp_error or 'unknown'}",
        )

    if _whatsapp_configured() and whatsapp_error:
        return False, f"WhatsApp OTP failed: {whatsapp_error}"

    return True, None


def create_otp_record(db: Session, phone_number: str) -> str:
    # Default-OTP mode: skip bcrypt hashing + OTP row writes (very slow on Vercel).
    if settings.USE_DEFAULT_OTP:
        return settings.DEFAULT_OTP

    otp = generate_otp(settings.OTP_LENGTH)
    otp_hash = hash_otp(otp)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    # Invalidate old OTPs for this number
    db.query(OTPRecord).filter(
        OTPRecord.phone_number == phone_number,
        OTPRecord.is_used == False,
    ).update({"is_used": True})

    record = OTPRecord(
        phone_number=phone_number,
        otp_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return otp


def verify_otp(db: Session, phone_number: str, otp: str) -> bool:
    # Fixed default OTP path — no bcrypt, no SMS (fast on serverless)
    if settings.USE_DEFAULT_OTP and otp == settings.DEFAULT_OTP:
        logger.info("otp_verified_default", phone=phone_number)
        return True

    record = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.phone_number == phone_number,
            OTPRecord.is_used == False,
            OTPRecord.expires_at > datetime.utcnow(),
        )
        .order_by(OTPRecord.created_at.desc())
        .first()
    )
    if not record:
        return False
    if record.attempts >= 3:
        return False

    record.attempts += 1
    if not verify_otp_hash(otp, record.otp_hash):
        db.commit()
        return False

    record.is_used = True
    db.commit()
    return True


def get_or_create_user(db: Session, phone_number: str) -> User:
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        user = User(phone_number=phone_number, registration_step=RegistrationStep.PENDING)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def register_user(
    db: Session, phone_number: str, business_name: str, gst_number: str | None = None
) -> User:
    from app.models.user import UserRole
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        user = User(phone_number=phone_number)
        db.add(user)
    user.business_name = business_name
    user.gst_number = gst_number
    user.registration_step = RegistrationStep.COMPLETED
    # Only assign role if not already set to owner/admin
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        # First completed user becomes OWNER, rest are CUSTOMER
        owner_exists = db.query(User).filter(
            User.role == UserRole.OWNER,
            User.id != user.id
        ).first()
        user.role = UserRole.OWNER if not owner_exists else UserRole.CUSTOMER
    db.commit()
    db.refresh(user)
    return user
