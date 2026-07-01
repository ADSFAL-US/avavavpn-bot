"""SQLAlchemy models for Avava VPN Bot."""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Float,
    ForeignKey, BigInteger, func
)
from sqlalchemy.orm import relationship
from db.engine import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime, server_default=func.now(), nullable=False)
    banned = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(Text, nullable=True)
    ban_expires = Column(DateTime, nullable=True)
    referral_code = Column(String(100), unique=True, nullable=True)
    referral_days = Column(Float, default=0, nullable=False)
    referred_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    has_used_discount = Column(Boolean, default=False, nullable=False)
    has_rewarded_referrer = Column(Boolean, default=False, nullable=False)

    # Relationships
    subscriptions = relationship("Subscription", back_populates="user", lazy="selectin")
    referrer = relationship("User", remote_side=[user_id], backref="referrals")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "is_admin": self.is_admin,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "banned": self.banned,
            "ban_reason": self.ban_reason,
            "ban_expires": self.ban_expires.isoformat() if self.ban_expires else None,
            "referral_code": self.referral_code,
            "referral_days": self.referral_days,
            "referred_by": self.referred_by,
            "has_used_discount": self.has_used_discount,
            "has_rewarded_referrer": self.has_rewarded_referrer,
        }


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    tariff_id = Column(String(50), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    ends_at = Column(DateTime, nullable=True)
    speed_mbps = Column(Float, nullable=True)
    traffic_used_mb = Column(Float, default=0, nullable=False)
    traffic_limit_mb = Column(Float, nullable=True)
    warp_enabled = Column(Boolean, default=False, nullable=False)
    test_configs_enabled = Column(Boolean, default=False, nullable=False)
    panel_subscription_id = Column(Integer, nullable=True)
    panel_sub_token = Column(String(255), nullable=True)
    payment_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="subscriptions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tariff_id": self.tariff_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "speed_mbps": self.speed_mbps,
            "traffic_used_mb": self.traffic_used_mb,
            "traffic_limit_mb": self.traffic_limit_mb,
            "warp_enabled": self.warp_enabled,
            "test_configs_enabled": self.test_configs_enabled,
            "panel_subscription_id": self.panel_subscription_id,
            "panel_sub_token": self.panel_sub_token,
            "payment_id": self.payment_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VPNConnection(Base):
    __tablename__ = "vpn_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    connected_at = Column(DateTime, server_default=func.now(), nullable=False)
    disconnected_at = Column(DateTime, nullable=True)
    bytes_in = Column(BigInteger, default=0)
    bytes_out = Column(BigInteger, default=0)


class SpeedUpgrade(Base):
    __tablename__ = "speed_upgrades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    requested_mbps = Column(Float, nullable=False)
    additional_payment = Column(Float, default=0)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, server_default=func.now())
    approved_at = Column(DateTime, nullable=True)


class AdminLog(Base):
    __tablename__ = "admin_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    action = Column(String(100), nullable=False)
    target_user_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    tariff_id = Column(String(50), nullable=False)
    payment_id = Column(String(100), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    metadata_json = Column(Text, nullable=True)  # JSON
