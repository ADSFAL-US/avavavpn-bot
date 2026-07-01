"""Admin repository with business logic."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories import BaseRepository
from db.models import User, AdminLog
from typing import List, Dict, Any


class AdminRepository(BaseRepository[AdminLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AdminLog)

    async def log_action(self, admin_id: int, action: str, target_user_id: int = None, details: str = None) -> AdminLog:
        log = AdminLog(
            admin_id=admin_id,
            action=action,
            target_user_id=target_user_id,
            details=details,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(AdminLog, User.first_name, User.username)
            .join(User, AdminLog.admin_id == User.user_id, isouter=True)
            .order_by(AdminLog.created_at.desc(), AdminLog.id.desc())
            .limit(limit)
        )
        logs = []
        for log, admin_first_name, admin_username in result.all():
            logs.append({
                "id": log.id,
                "admin_id": log.admin_id,
                "action": log.action,
                "target_user_id": log.target_user_id,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "admin_first_name": admin_first_name,
                "admin_username": admin_username,
            })
        return logs

    async def get_subscription_stats(self) -> dict:
        from database import TARIFFS
        from db.models import Subscription
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

    async def get_user_count(self) -> int:
        result = await self.session.execute(select(func.count(User.user_id)))
        return result.scalar()

    async def get_active_subscription_count(self) -> int:
        from db.models import Subscription
        result = await self.session.execute(
            select(func.count(Subscription.id)).where(Subscription.status == "active")
        )
        return result.scalar()
