import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class MessageType(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    encrypted_content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), nullable=False)
    whatsapp_message_id = Column(String(255), nullable=True, unique=True)
    transcription = Column(Text, nullable=True)
    is_inbound = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="messages")
    transaction = relationship("Transaction", back_populates="message")
