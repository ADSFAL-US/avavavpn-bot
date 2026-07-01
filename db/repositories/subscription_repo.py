"""Subscription repository with business logic."""
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories import BaseRepository
from db.models import Subscription
from datetime import datetime, timedelta
from typing import Optional, List
from database import TARIFFS
import re


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Subscription)

    async def create(self, user_id: int, tariff_id: str, **kwargs) -> Subscription:
        tariff = TARIFFS.get(tariff_id)
        if not tariff:
            raise ValueError(f"Unknown tariff: {tariff_id}")

        ends_at = kwargs.get("ends_at")
        expiry_days = kwargs.get("expiry_days")
        
        if ends_at is None:
            if expiry_days is not None:
                ends_at = datetime.now() + timedelta(days=expiry_days)
            else:
                ends_at = datetime.now() + timedelta(days=tariff["duration_days"])

        sub = Subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            ends_at=ends_at,
            speed_mbps=kwargs.get("speed_mbps") or self._parse_speed(tariff["speed"]),
            traffic_limit_mb=tariff.get("traffic_limit_gb", 0) * 1024 if tariff.get("traffic_limit_gb") else None,
            warp_enabled=tariff.get("warp", False),
            test_configs_enabled=tariff.get("test_configs", False),
            panel_subscription_id=kwargs.get("panel_subscription_id"),
            panel_sub_token=kwargs.get("panel_sub_token"),
            payment_id=kwargs.get("payment_id"),
        )
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def get_by_id(self, sub_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == sub_id)
        )
        return result.scalar_one_or_none()

    async def get_active(self, user_id: int) -> Optional[Subscription]:
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

    async def extend(self, sub_id: int, extra_days: int) -> bool:
        sub = await self.get_by_id(sub_id)
        if not sub or not sub.ends_at:
            return False

        new_end = sub.ends_at + timedelta(days=extra_days)
        result = await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(ends_at=new_end)
        )
        return result.rowcount > 0

    async def cancel(self, sub_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id, Subscription.user_id == user_id)
            .values(status="cancelled")
        )
        return result.rowcount > 0

    async def change_tariff(self, sub_id: int, new_tariff_id: str, expiry_days: int = None) -> Optional[Subscription]:
        """Cancel old, create new - in single transaction."""
        old_sub = await self.get_by_id(sub_id)
        if not old_sub:
            return None

        # Cancel old
        old_sub.status = "cancelled"

        # Create new
        new_sub = await self.create(
            user_id=old_sub.user_id,
            tariff_id=new_tariff_id,
            expiry_days=expiry_days,
        )
        return new_sub

    async def get_active_count(self) -> int:
        result = await self.session.execute(
            select(func.count(Subscription.id)).where(Subscription.status == "active")
        )
        return result.scalar()

    async def get_subscription_stats(self) -> dict:
        result = await self.session.execute(
            select(Subscription.tariff_id, func.count(Subscription.id))
            .where(Subscription.status == "active")
            .group_by(Subscription.tariff_id)
        )
        stats = {}
        for tariff_id, count in result.all():
            tariff = TARIFFS.get(tariff_id, {})
            stats[tariff_id] = {
                "name": tariff.get("name", tariff_id),
                "active_count": count,
            }
        return stats

    def _parse_speed(self, speed_str: str) -> float:
        match = re.search(r'(\d+)', speed_str)
        return float(match.group(1)) if match else 50.0
