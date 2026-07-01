#!/usr/bin/env python3
"""One-time migration from raw sqlite3 to SQLAlchemy."""
import asyncio
import sqlite3
import json
import sys
import os
import uuid
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.engine import engine, async_session_maker, Base
from db.models import User, Subscription, VPNConnection, SpeedUpgrade, AdminLog, Payment


def parse_datetime(value):
    """Parse datetime string from SQLite to Python datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # Try common formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # If all else fails, try fromisoformat (handles ISO format with/without microseconds)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def migrate():
    """Migrate data from old database to new SQLAlchemy models."""
    print("Starting migration...")
    
    # 1. Create new tables
    print("Creating new tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Read from old DB
    old_db_path = "data/avava_vpn.db"
    if not os.path.exists(old_db_path):
        print(f"Old database not found at {old_db_path}")
        return
    
    old_conn = sqlite3.connect(old_db_path)
    old_conn.row_factory = sqlite3.Row
    cursor = old_conn.cursor()
    
    async with async_session_maker() as session:
        # Users
        print("Migrating users...")
        cursor.execute("SELECT * FROM users")
        users_count = 0
        for row in cursor.fetchall():
            # Handle missing columns in old schema
            referral_code = row["referral_code"] if "referral_code" in row.keys() else f"REF_{row['user_id']}_{uuid.uuid4().hex[:6]}"
            referral_days = row["referral_days"] if "referral_days" in row.keys() else 0
            referred_by = row["referred_by"] if "referred_by" in row.keys() else None
            has_used_discount = bool(row["has_used_discount"]) if "has_used_discount" in row.keys() else False
            has_rewarded_referrer = bool(row["has_rewarded_referrer"]) if "has_rewarded_referrer" in row.keys() else False
            
            user = User(
                user_id=row["user_id"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                phone=row["phone"],
                is_admin=bool(row["is_admin"]),
                registered_at=parse_datetime(row["registered_at"]),
                banned=bool(row["banned"]),
                ban_reason=row["ban_reason"],
                ban_expires=parse_datetime(row["ban_expires"]),
                referral_code=referral_code,
                referral_days=referral_days,
                referred_by=referred_by,
                has_used_discount=has_used_discount,
                has_rewarded_referrer=has_rewarded_referrer,
            )
            session.add(user)
            users_count += 1
        print(f"  Migrated {users_count} users")
        
        # Subscriptions
        print("Migrating subscriptions...")
        cursor.execute("SELECT * FROM subscriptions")
        subs_count = 0
        for row in cursor.fetchall():
            # Handle missing columns in old schema
            test_configs_enabled = bool(row["test_configs_enabled"]) if "test_configs_enabled" in row.keys() else False
            panel_subscription_id = row["panel_subscription_id"] if "panel_subscription_id" in row.keys() else None
            panel_sub_token = row["panel_sub_token"] if "panel_sub_token" in row.keys() else None
            payment_id = row["payment_id"] if "payment_id" in row.keys() else None
            
            sub = Subscription(
                id=row["id"],
                user_id=row["user_id"],
                tariff_id=row["tariff_id"],
                status=row["status"],
                started_at=parse_datetime(row["started_at"]),
                ends_at=parse_datetime(row["ends_at"]),
                speed_mbps=row["speed_mbps"],
                traffic_used_mb=row["traffic_used_mb"] or 0,
                traffic_limit_mb=row["traffic_limit_mb"],
                warp_enabled=bool(row["warp_enabled"]),
                test_configs_enabled=test_configs_enabled,
                panel_subscription_id=panel_subscription_id,
                panel_sub_token=panel_sub_token,
                payment_id=payment_id,
                created_at=parse_datetime(row["created_at"]),
            )
            session.add(sub)
            subs_count += 1
        print(f"  Migrated {subs_count} subscriptions")
        
        # VPN Connections
        print("Migrating VPN connections...")
        try:
            cursor.execute("SELECT * FROM vpn_connections")
            vpn_count = 0
            for row in cursor.fetchall():
                vpn = VPNConnection(
                    id=row["id"],
                    user_id=row["user_id"],
                    subscription_id=row["subscription_id"],
                    ip_address=row["ip_address"],
                    connected_at=parse_datetime(row["connected_at"]),
                    disconnected_at=parse_datetime(row["disconnected_at"]),
                    bytes_in=row["bytes_in"] or 0,
                    bytes_out=row["bytes_out"] or 0,
                )
                session.add(vpn)
                vpn_count += 1
            print(f"  Migrated {vpn_count} VPN connections")
        except sqlite3.OperationalError:
            print("  VPN connections table not found, skipping")
        
        # Speed Upgrades
        print("Migrating speed upgrades...")
        try:
            cursor.execute("SELECT * FROM speed_upgrades")
            speed_count = 0
            for row in cursor.fetchall():
                speed = SpeedUpgrade(
                    id=row["id"],
                    user_id=row["user_id"],
                    subscription_id=row["subscription_id"],
                    requested_mbps=row["requested_mbps"],
                    additional_payment=row["additional_payment"] or 0,
                    status=row["status"],
                    created_at=parse_datetime(row["created_at"]),
                    approved_at=parse_datetime(row["approved_at"]),
                )
                session.add(speed)
                speed_count += 1
            print(f"  Migrated {speed_count} speed upgrades")
        except sqlite3.OperationalError:
            print("  Speed upgrades table not found, skipping")
        
        # Admin Log
        print("Migrating admin logs...")
        try:
            cursor.execute("SELECT * FROM admin_log")
            log_count = 0
            for row in cursor.fetchall():
                log = AdminLog(
                    id=row["id"],
                    admin_id=row["admin_id"],
                    action=row["action"],
                    target_user_id=row["target_user_id"],
                    details=row["details"],
                    created_at=parse_datetime(row["created_at"]),
                )
                session.add(log)
                log_count += 1
            print(f"  Migrated {log_count} admin logs")
        except sqlite3.OperationalError:
            print("  Admin log table not found, skipping")
        
        # Payments (from yookassa table)
        print("Migrating payments...")
        try:
            cursor.execute("SELECT * FROM payments")
            pay_count = 0
            for row in cursor.fetchall():
                payment = Payment(
                    id=row["id"],
                    order_id=row["order_id"],
                    user_id=row["user_id"],
                    tariff_id=row["tariff_id"],
                    payment_id=row["payment_id"],
                    amount=row["amount"],
                    status=row["status"],
                    created_at=parse_datetime(row["created_at"]),
                    updated_at=parse_datetime(row["updated_at"]),
                    metadata_json=row["metadata"],
                )
                session.add(payment)
                pay_count += 1
            print(f"  Migrated {pay_count} payments")
        except sqlite3.OperationalError:
            print("  Payments table not found, skipping")
        
        await session.commit()
    
    old_conn.close()
    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(migrate())