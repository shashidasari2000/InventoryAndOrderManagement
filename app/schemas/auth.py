from pydantic import BaseModel, field_validator
import re


class RegisterRequest(BaseModel):
    phone_number: str
    business_name: str
    gst_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"\D", "", v)
        if not re.match(r"^(\+91|91)?[6-9]\d{9}$", cleaned):
            raise ValueError("Invalid Indian mobile number")
        if not cleaned.startswith("+"):
            if cleaned.startswith("91") and len(cleaned) == 12:
                cleaned = "+" + cleaned
            else:
                cleaned = "+91" + cleaned[-10:]
        return cleaned


class OTPRequest(BaseModel):
    phone_number: str


class OTPVerifyRequest(BaseModel):
    phone_number: str
    otp: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    business_name: str | None
    phone_number: str
    role: str = "owner"
