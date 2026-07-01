"""Tests for PaymentRepository."""
import pytest
import json


class TestPaymentRepository:
    """Test PaymentRepository methods."""

    @pytest.mark.asyncio
    async def test_create_payment(self, payment_repo, user_repo, sample_user_data):
        """Test creating a payment record."""
        user = await user_repo.get_or_create(sample_user_data)
        
        payment = await payment_repo.create(
            order_id="test_order_123",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
            payment_id="pay_123",
            metadata={"test": "data"}
        )
        
        assert payment.id is not None
        assert payment.order_id == "test_order_123"
        assert payment.user_id == user.user_id
        assert payment.tariff_id == "basic"
        assert payment.amount == 99.0
        assert payment.payment_id == "pay_123"
        assert payment.status == "pending"
        assert payment.metadata_json is not None
        metadata = json.loads(payment.metadata_json)
        assert metadata["test"] == "data"

    @pytest.mark.asyncio
    async def test_get_by_order_id(self, payment_repo, user_repo, sample_user_data):
        """Test getting payment by order ID."""
        user = await user_repo.get_or_create(sample_user_data)
        created = await payment_repo.create(
            order_id="test_order_456",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
        )
        
        found = await payment_repo.get_by_order_id("test_order_456")
        
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_get_by_order_id_not_found(self, payment_repo):
        """Test getting non-existent payment by order ID."""
        found = await payment_repo.get_by_order_id("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_payment_id(self, payment_repo, user_repo, sample_user_data):
        """Test getting payment by YooKassa payment ID."""
        user = await user_repo.get_or_create(sample_user_data)
        created = await payment_repo.create(
            order_id="test_order_789",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
            payment_id="pay_789",
        )
        
        found = await payment_repo.get_by_payment_id("pay_789")
        
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_mark_completed_atomic(self, payment_repo, user_repo, sample_user_data):
        """Test atomic mark completed - prevents double processing."""
        user = await user_repo.get_or_create(sample_user_data)
        await payment_repo.create(
            order_id="test_order_atomic",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
            payment_id="pay_atomic",
        )
        
        # First call should succeed
        result1 = await payment_repo.mark_completed("test_order_atomic", "pay_atomic")
        assert result1 is True
        
        # Second call should fail (already completed)
        result2 = await payment_repo.mark_completed("test_order_atomic", "pay_atomic")
        assert result2 is False

    @pytest.mark.asyncio
    async def test_mark_completed_nonexistent(self, payment_repo):
        """Test marking non-existent payment as completed."""
        result = await payment_repo.mark_completed("nonexistent", "pay_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_pending_for_user(self, payment_repo, user_repo, sample_user_data):
        """Test getting pending payments for user."""
        user = await user_repo.get_or_create(sample_user_data)
        
        await payment_repo.create(
            order_id="pending_1",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
        )
        await payment_repo.create(
            order_id="pending_2",
            user_id=user.user_id,
            tariff_id="premium",
            amount=199.0,
        )
        
        pending = await payment_repo.get_pending_for_user(user.user_id)
        
        assert len(pending) == 2
        assert all(p.status == "pending" for p in pending)

    @pytest.mark.asyncio
    async def test_get_pending_for_user_empty(self, payment_repo, user_repo, sample_user_data):
        """Test getting pending payments when none exist."""
        user = await user_repo.get_or_create(sample_user_data)
        
        pending = await payment_repo.get_pending_for_user(user.user_id)
        
        assert pending == []

    @pytest.mark.asyncio
    async def test_clean_old_payments(self, payment_repo, user_repo, sample_user_data):
        """Test cleaning old pending payments."""
        user = await user_repo.get_or_create(sample_user_data)
        
        # Create old payment (manually set created_at)
        from datetime import datetime, timedelta
        from sqlalchemy import update
        from db.models import Payment
        
        payment = await payment_repo.create(
            order_id="old_payment",
            user_id=user.user_id,
            tariff_id="basic",
            amount=99.0,
        )
        
        # Update created_at to be old
        async with payment_repo.session.begin():
            await payment_repo.session.execute(
                update(Payment)
                .where(Payment.id == payment.id)
                .values(created_at=datetime.now() - timedelta(hours=48))
            )
        
        cleaned = await payment_repo.clean_old_payments(hours=24)
        
        assert cleaned == 1
        
        # Verify it's gone
        found = await payment_repo.get_by_order_id("old_payment")
        assert found is None