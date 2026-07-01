"""Payment repository with business logic."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories import BaseRepository
from db.models import Payment
from typing import Optional, List, Dict
import json


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Payment)

    async def create(self, order_id: str, user_id: int, tariff_id: str,
                     amount: float, payment_id: str = None, metadata: Dict = None) -> Payment:
        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            tariff_id=tariff_id,
            amount=amount,
            payment_id=payment_id,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_order_id(self, order_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_payment_id(self, payment_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        return result.scalar_one_or_none()

    async def mark_completed(self, order_id: str, payment_id: str = None) -> bool:
        """ATOMIC: Only mark completed if still pending - prevents double processing."""
        result = await self.session.execute(
            update(Payment)
            .where(Payment.order_id == order_id, Payment.status == "pending")
            .values(status="completed", payment_id=payment_id)
        )
        return result.rowcount > 0  # Returns False if already processed

    async def get_pending_for_user(self, user_id: int) -> List[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.user_id == user_id, Payment.status == "pending")
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def clean_old_payments(self, hours: int = 24) -> int:
        """Clean expired pending payments."""
        from datetime import datetime, timedelta
        from sqlalchemy import delete
        cutoff = datetime.now() - timedelta(hours=hours)
        result = await self.session.execute(
            delete(Payment)
            .where(Payment.status == "pending", Payment.created_at < cutoff)
        )
        return result.rowcount
