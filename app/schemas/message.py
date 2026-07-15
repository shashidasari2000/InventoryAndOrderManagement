from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from app.models.message import MessageType


class MessageOut(BaseModel):
    id: UUID
    message_type: MessageType
    decrypted_content: str
    is_inbound: bool
    created_at: datetime
    transaction_id: UUID | None = None

    class Config:
        from_attributes = True


class MessageList(BaseModel):
    total: int
    items: list[MessageOut]


class SupportAccessRequest(BaseModel):
    duration: str  # "24h" | "7d"


class SupportAccessOut(BaseModel):
    id: UUID
    expires_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
