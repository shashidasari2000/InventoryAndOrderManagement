import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    SUPPORT = "support"
    CUSTOMER = "customer"


class RegistrationStep(str, enum.Enum):
    PENDING = "pending"
    AWAITING_DETAILS = "awaiting_details"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    business_name = Column(String(255), nullable=True)
    gst_number = Column(String(20), nullable=True)
    # Invoice settings
    business_address = Column(String(500), nullable=True)
    business_phone = Column(String(20), nullable=True)
    business_email = Column(String(100), nullable=True)
    business_state = Column(String(50), nullable=True)
    invoice_prefix = Column(String(10), default="INV")
    invoice_next_number = Column(String(20), default="1")
    show_gst_on_invoice = Column(Boolean, default=True)
    signature_image = Column(Text, nullable=True)  # Base64 encoded signature image
    role = Column(Enum(UserRole), default=UserRole.CUSTOMER, nullable=False)
    is_active = Column(Boolean, default=True)
    registration_step = Column(
        Enum(RegistrationStep), default=RegistrationStep.PENDING, nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    transactions = relationship("Transaction", back_populates="user", lazy="dynamic")
    messages = relationship("Message", back_populates="user", lazy="dynamic")
    audit_logs = relationship("AuditLog", back_populates="user", lazy="dynamic")
    support_accesses = relationship(
        "SupportAccess", back_populates="user", lazy="dynamic"
    )
    products = relationship("Product", back_populates="user", lazy="dynamic")
    suppliers = relationship("Supplier", back_populates="user", lazy="dynamic")
    buyer_orders = relationship("BuyerOrder", back_populates="user", lazy="dynamic")
