"""User repository with business logic."""
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories import BaseRepository
from db.models import User, Subscription
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import re


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_or_create(self, user_data: Dict[str, Any]) -> User:
        """Get existing user or create new with referral code."""
        user_id = user_data["user_id"]
        user = await self.get_by_id(user_id)
        if user:
            return user

        referral_code = f"REF_{user_id}_{uuid.uuid4().hex[:6]}"
        referred_by = user_data.get("referred_by")

        user = User(
            user_id=user_id,
            username=user_data.get("username", ""),
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name", ""),
            referral_code=referral_code,
            referred_by=referred_by,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def is_admin(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        return user and user.is_admin

    async def set_admin(self, user_id: int) -> bool:
        result = await self.session.execute(
            update(User).where(User.user_id == user_id).values(is_admin=True)
        )
        return result.rowcount > 0

    async def remove_admin(self, user_id: int) -> bool:
        result = await self.session.execute(
            update(User).where(User.user_id == user_id).values(is_admin=False)
        )
        return result.rowcount > 0

    async def add_referral_days(self, user_id: int, days: float) -> bool:
        # Atomic update
        result = await self.session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(referral_days=User.referral_days + days)
        )
        return result.rowcount > 0

    async def reward_referrer(self, user_id: int, tariff_id: str) -> bool:
        """Atomic referrer reward - single UPDATE with WHERE conditions."""
        user = await self.get_by_id(user_id)
        if not user or not user.referred_by or user.has_rewarded_referrer:
            return False
        if user.referred_by == user_id:
            return False

        # Atomic: add days + mark rewarded in one query
        result = await self.session.execute(
            update(User)
            .where(User.user_id == user.referred_by)
            .values(referral_days=User.referral_days + 7)
        )
        if result.rowcount == 0:
            return False

        # Mark user as rewarded
        await self.session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(has_rewarded_referrer=True)
        )

        # Mark discount used for paid tariffs
        if tariff_id != "trial":
            await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(has_used_discount=True)
            )

        return True

    async def get_active_subscription(self, user_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == "active")
            .order_by(Subscription.id.desc())
        )
        return result.scalar_one_or_none()

    async def get_user_subscriptions(self, user_id: int) -> List[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.id.desc())
        )
        return list(result.scalars().all())

    async def ban_user(self, user_id: int, reason: str = None, duration_days: int = None) -> bool:
        if duration_days:
            expires = datetime.now() + timedelta(days=duration_days)
            result = await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(banned=True, ban_reason=reason, ban_expires=expires)
            )
        else:
            result = await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(banned=True, ban_reason=reason, ban_expires=None)
            )
        return result.rowcount > 0

    async def unban_user(self, user_id: int) -> bool:
        result = await self.session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(banned=False, ban_reason=None, ban_expires=None)
        )
        return result.rowcount > 0

    async def get_all_users(self, offset: int = 0, limit: int = 100) -> List[User]:
        result = await self.session.execute(
            select(User).order_by(User.registered_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def get_user_count(self) -> int:
        result = await self.session.execute(select(func.count(User.user_id)))
        return result.scalar()

    async def has_user_ever_had_tariff(self, user_id: int, tariff_id: str) -> bool:
        result = await self.session.execute(
            select(func.count(Subscription.id))
            .where(Subscription.user_id == user_id, Subscription.tariff_id == tariff_id)
        )
        return result.scalar() > 0

    def _parse_speed(self, speed_str: str) -> float:
        match = re.search(r'(\d+)', speed_str)
        return float(match.group(1)) if match else 50.0
