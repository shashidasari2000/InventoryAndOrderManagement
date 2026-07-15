from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.schemas.auth import RegisterRequest, OTPRequest, OTPVerifyRequest, TokenResponse
from app.services import auth_service
from app.models.user import User, RegistrationStep
import structlog
import base64
from io import BytesIO

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _remove_signature_background(b64_image: str) -> str:
    """Remove white/light background from signature image, return transparent PNG as base64."""
    try:
        from PIL import Image

        # Decode base64
        img_data = base64.b64decode(b64_image.split(',')[-1])
        img = Image.open(BytesIO(img_data)).convert("RGBA")

        data = img.getdata()
        new_data = []
        for r, g, b, a in data:
            # Make light/white pixels transparent
            if r > 200 and g > 200 and b > 200:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append((r, g, b, a))

        img.putdata(new_data)

        # Save as PNG base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return b64_image


@router.post("/register", response_model=dict, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_user(
        db,
        phone_number=payload.phone_number,
        business_name=payload.business_name,
        gst_number=payload.gst_number,
    )
    logger.info("user_registered", phone=payload.phone_number)
    return {
        "message": "Registration successful.",
        "phone_number": payload.phone_number,
    }


@router.post("/request-otp", response_model=dict)
def request_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    from app.config import get_settings
    settings = get_settings()

    # Ensure user exists (needed for verify)
    user = db.query(auth_service.User).filter(
        auth_service.User.phone_number == payload.phone_number
    ).first()
    if not user:
        user = auth_service.get_or_create_user(db, payload.phone_number)

    # Fast path for tablet/demo: no bcrypt, no SMS providers
    if settings.USE_DEFAULT_OTP:
        return {
            "message": "Use default OTP to sign in",
            "otp_sent": True,
            "default_otp": settings.DEFAULT_OTP,
        }

    otp = auth_service.create_otp_record(db, payload.phone_number)
    sent, error_msg = auth_service.send_otp(payload.phone_number, otp)
    if not sent:
        logger.error("otp_send_failed", phone=payload.phone_number, error=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg or "Failed to send OTP")

    return {"message": "OTP sent", "otp_sent": sent}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    valid = auth_service.verify_otp(db, payload.phone_number, payload.otp)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP"
        )

    user = db.query(auth_service.User).filter(
        auth_service.User.phone_number == payload.phone_number
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token = auth_service.create_access_token({"sub": str(user.id), "phone": user.phone_number})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        business_name=user.business_name,
        phone_number=user.phone_number,
        role=user.role.value,
    )


@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user profile with invoice settings."""
    return {
        "id": str(current_user.id),
        "phone_number": current_user.phone_number,
        "business_name": current_user.business_name,
        "gst_number": current_user.gst_number,
        "business_address": current_user.business_address,
        "business_phone": current_user.business_phone,
        "business_email": current_user.business_email,
        "business_state": current_user.business_state,
        "invoice_prefix": current_user.invoice_prefix,
        "invoice_next_number": current_user.invoice_next_number,
        "show_gst_on_invoice": current_user.show_gst_on_invoice,
        "signature_image": current_user.signature_image,
    }


@router.put("/profile")
def update_profile(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user profile and invoice settings."""
    allowed_fields = [
        "business_name", "gst_number", "business_address",
        "business_phone", "business_email", "business_state",
        "invoice_prefix", "invoice_next_number", "show_gst_on_invoice",
        "signature_image"
    ]
    
    for field in allowed_fields:
        if field in data:
            if field == "signature_image" and data[field]:
                data[field] = _remove_signature_background(data[field])
            setattr(current_user, field, data[field])
    
    db.commit()
    db.refresh(current_user)
    
    return {
        "id": str(current_user.id),
        "phone_number": current_user.phone_number,
        "business_name": current_user.business_name,
        "gst_number": current_user.gst_number,
        "business_address": current_user.business_address,
        "business_phone": current_user.business_phone,
        "business_email": current_user.business_email,
        "business_state": current_user.business_state,
        "invoice_prefix": current_user.invoice_prefix,
        "invoice_next_number": current_user.invoice_next_number,
        "show_gst_on_invoice": current_user.show_gst_on_invoice,
        "signature_image": current_user.signature_image,
    }
