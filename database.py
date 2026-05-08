# Avava VPN Bot - Database Model
import sqlite3
import logging
import uuid
from datetime import datetime, timedelta
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


# Tariff definitions
# preset_id: links to X-Controller subscription preset (1 = lowest/free, 3 = highest)
TARIFFS = {
    "trial": {
        "id": "trial",
        "name": "🧪 Пробник",
        "description": "Бесплатный тестовый тариф\n• Скорость: 50 Мбит/с\n• Трафик: до 50 ГБ\n• Срок: 3 дня\n• Warp: нет\n• Доступ к тестовым конфигам: нет",
        "price": 0,
        "currency": "бесплатно",
        "speed": "50 Мбит/с",
        "speed_upgrade": None,
        "traffic_limit_gb": 50,
        "duration_days": 3,
        "warp": False,
        "test_configs": False,  # No access to test configs
        "preset_id": 1,  # Free/basic preset
    },
    "basic": {
        "id": "basic",
        "name": "🛡️ Базовый минимум",
        "description": "Базовый тарифный план\n• Скорость: 50 Мбит/с\n• Трафик: без ограничений\n• Срок: 1 месяц\n• Warp: нет\n• Доступ к тестовым конфигам: да",
        "price": 99,
        "currency": "рублей в месяц",
        "speed": "50 Мбит/с",
        "speed_upgrade": None,  # No speed upgrades
        "traffic_limit_gb": None,
        "duration_days": 30,
        "warp": False,
        "test_configs": True,  # Access to test configs
        "preset_id": 2,  # Basic preset
    },
    "premium": {
        "id": "premium",
        "name": "💎 Роскошный максимум",
        "description": "Премиум тарифный план\n• Скорость: 100 Мбит/с\n• Трафик: без ограничений\n• Срок: 1 месяц\n• Warp: да\n• Доступ к тестовым конфигам: да",
        "price": 199,
        "currency": "рублей в месяц",
        "speed": "100 Мбит/с",
        "speed_upgrade": None,  # No speed upgrades
        "traffic_limit_gb": None,
        "duration_days": 30,
        "warp": True,
        "test_configs": True,  # Access to test configs
        "preset_id": 3,  # Premium preset
    },
}


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_PATH
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _create_tables(self):
        """Create all required tables."""
        cursor = self.conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                is_admin INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                ban_expires TIMESTAMP,
                referral_code TEXT UNIQUE,
                referral_days REAL DEFAULT 0,
                referred_by INTEGER,
                has_used_discount BOOLEAN DEFAULT 0,
                has_rewarded_referrer BOOLEAN DEFAULT 0
            )
        """)

        # Subscriptions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tariff_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ends_at TIMESTAMP,
                speed_mbps REAL,
                traffic_used_mb REAL DEFAULT 0,
                traffic_limit_mb REAL,
                warp_enabled INTEGER DEFAULT 0,
                test_configs_enabled INTEGER DEFAULT 0,
                panel_subscription_id INTEGER,
                panel_sub_token TEXT,
                payment_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Migration: add new columns if they don't exist
        try:
            cursor.execute("SELECT panel_subscription_id FROM subscriptions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN panel_subscription_id INTEGER")
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN panel_sub_token TEXT")
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN payment_id TEXT")
            self.conn.commit()
            logger.info("Migrated subscriptions table with panel fields")
        except Exception as e:
            logger.warning(f"Migration check error (may be already migrated): {e}")
        
        # Add test_configs_enabled column
        try:
            cursor.execute("SELECT test_configs_enabled FROM subscriptions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN test_configs_enabled INTEGER DEFAULT 0")
            self.conn.commit()
            logger.info("Migrated subscriptions table with test_configs_enabled field")
        except Exception as e:
            logger.warning(f"Migration check for test_configs_enabled failed (may be already migrated): {e}")

        # Add referral_code column and generate codes for existing users
        try:
            cursor.execute("SELECT referral_code FROM users LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE")
            self.conn.commit()
            logger.info("Added referral_code column to users table")
            
            # Generate referral codes for existing users
            cursor.execute("SELECT user_id FROM users WHERE referral_code IS NULL")
            users_without_code = cursor.fetchall()
            
            for user_row in users_without_code:
                user_id = user_row["user_id"]
                referral_code = f"REF_{user_id}_{uuid.uuid4().hex[:6]}"
                cursor.execute(
                    "UPDATE users SET referral_code = ? WHERE user_id = ?",
                    (referral_code, user_id)
                )
            
            self.conn.commit()
            logger.info(f"Generated referral codes for {len(users_without_code)} existing users")
        except Exception as e:
            logger.warning(f"Migration check for referral_code failed (may be already migrated): {e}")

        # VPN connections table (for tracking active connections)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vpn_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER,
                ip_address TEXT,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                disconnected_at TIMESTAMP,
                bytes_in REAL DEFAULT 0,
                bytes_out REAL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """)

        # Speed upgrade requests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS speed_upgrades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                requested_mbps REAL NOT NULL,
                additional_payment REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """)

        # Admin activity log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    def get_or_create_user(self, user_data):
        """Get existing user or create a new one."""
        user_id = user_data.get("user_id")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            return dict(user)
        
        # Create new user with referral code
        first_name = user_data.get("first_name", "")
        username = user_data.get("username", "")
        last_name = user_data.get("last_name", "")
        referral_code = f"REF_{user_id}_{uuid.uuid4().hex[:6]}"
        
        cursor.execute(
            """INSERT INTO users (user_id, username, first_name, last_name, referral_code)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, first_name, last_name, referral_code)
        )
        self.conn.commit()
        
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "phone": None,
            "is_admin": 0,
            "registered_at": datetime.now().isoformat(),
            "banned": 0,
            "ban_reason": None,
            "ban_expires": None,
            "referral_code": referral_code,
            "referral_days": 0,
            "referred_by": None,
            "has_used_discount": False,
            "has_rewarded_referrer": False
        }

    def is_admin(self, user_id):
        """Check if a user is an admin."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row and row["is_admin"] == 1

    def set_admin(self, user_id):
        """Promote a user to admin."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def remove_admin(self, user_id):
        """Remove admin status from a user."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_active_subscription(self, user_id):
        """Get the active subscription for a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM subscriptions
               WHERE user_id = ? AND status = 'active'
               ORDER BY id DESC LIMIT 1""",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_subscription_by_id(self, subscription_id):
        """Get subscription by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM subscriptions WHERE id = ?",
            (subscription_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_subscriptions(self, user_id):
        """Get all subscriptions for a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def create_subscription(
        self,
        user_id,
        tariff_id,
        ends_at=None,
        speed_mbps=None,
        traffic_limit_mb=None,
        warp_enabled=None,
        test_configs_enabled=None,
        panel_subscription_id=None,
        panel_sub_token=None,
        payment_id=None,
    ):
        """Create a new subscription for a user with full panel integration."""
        tariff = TARIFFS.get(tariff_id)
        if not tariff:
            raise ValueError(f"Unknown tariff: {tariff_id}")

        now = datetime.now()
        if ends_at is None:
            ends_at = now + timedelta(days=tariff["duration_days"])
        
        if traffic_limit_mb is None and tariff["traffic_limit_gb"]:
            traffic_limit_mb = tariff["traffic_limit_gb"] * 1024  # GB to MB
        
        if speed_mbps is None:
            speed_mbps = self._parse_speed(tariff["speed"])
        
        if warp_enabled is None:
            warp_enabled = int(tariff["warp"])
        if test_configs_enabled is None:
            test_configs_enabled = int(tariff.get("test_configs", False))
        
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO subscriptions 
               (user_id, tariff_id, status, ends_at, speed_mbps, 
                traffic_limit_mb, warp_enabled, test_configs_enabled,
                panel_subscription_id, panel_sub_token, payment_id)
               VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, tariff_id,
                ends_at.isoformat() if ends_at else None,
                speed_mbps,
                traffic_limit_mb,
                warp_enabled,
                test_configs_enabled,
                panel_subscription_id,
                panel_sub_token,
                payment_id,
            )
        )
        subscription_id = cursor.lastrowid
        self.conn.commit()

        logger.info(
            f"Created subscription: id={subscription_id}, user={user_id}, "
            f"tariff={tariff_id}, panel_id={panel_subscription_id}"
        )
        
        return {
            "id": subscription_id,
            "status": "created",
            "panel_subscription_id": panel_subscription_id,
            "panel_sub_token": panel_sub_token,
        }

    def cancel_subscription(self, subscription_id, user_id):
        """Cancel a subscription."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE id = ? AND user_id = ?",
            (subscription_id, user_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def cancel_subscription_by_tariff(self, tariff_id):
        """Cancel subscription by tariff ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE tariff_id = ? AND status = 'active'",
            (tariff_id,)
        )
        self.conn.commit()
        return cursor.rowcount

    def update_speed(self, subscription_id, speed_mbps):
        """Update the speed for a subscription."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET speed_mbps = ? WHERE id = ?",
            (speed_mbps, subscription_id)
        )
        self.conn.commit()

    def update_traffic_used(self, user_id, bytes_transferred):
        """Update traffic usage for a user."""
        mb_transferred = bytes_transferred / (1024 * 1024)  # bytes to MB
        
        cursor = self.conn.cursor()
        
        # Get current subscription
        cursor.execute(
            """SELECT id, traffic_used_mb FROM subscriptions 
               WHERE user_id = ? AND status = 'active'""",
            (user_id,)
        )
        sub = cursor.fetchone()
        
        if sub:
            new_used = (sub["traffic_used_mb"] or 0) + mb_transferred
            cursor.execute(
                "UPDATE subscriptions SET traffic_used_mb = ? WHERE id = ?",
                (new_used, sub["id"])
            )
            self.conn.commit()

    def get_user_count(self):
        """Get total number of users."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        return cursor.fetchone()["count"]

    def get_active_subscription_count(self):
        """Get count of active subscriptions."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'active'")
        return cursor.fetchone()["count"]

    def get_all_users(self, offset=0, limit=100):
        """Get all users with pagination."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM users ORDER BY registered_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_user_by_id(self, user_id):
        """Get a specific user by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def ban_user(self, user_id, reason=None, duration_days=None):
        """Ban a user."""
        cursor = self.conn.cursor()
        
        if duration_days:
            expires = datetime.now() + timedelta(days=duration_days)
            cursor.execute(
                "UPDATE users SET banned = 1, ban_reason = ?, ban_expires = ? WHERE user_id = ?",
                (reason, expires.isoformat(), user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET banned = 1, ban_reason = ?, ban_expires = NULL WHERE user_id = ?",
                (reason, user_id)
            )
        self.conn.commit()

    def unban_user(self, user_id):
        """Unban a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET banned = 0, ban_reason = NULL, ban_expires = NULL WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def log_admin_action(self, admin_id, action, target_user_id=None, details=None):
        """Log an admin action."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO admin_log (admin_id, action, target_user_id, details) VALUES (?, ?, ?, ?)",
            (admin_id, action, target_user_id, details)
        )
        self.conn.commit()

    def get_admin_logs(self, limit=50):
        """Get recent admin logs."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT l.*, u.first_name as admin_first_name, u.username as admin_username 
               FROM admin_log l 
               LEFT JOIN users u ON l.admin_id = u.user_id 
               ORDER BY l.created_at DESC LIMIT ?""",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def has_user_ever_had_tariff(self, user_id: int, tariff_id: str) -> bool:
        """Check if user has ever had a specific tariff."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM subscriptions WHERE user_id = ? AND tariff_id = ?",
            (user_id, tariff_id)
        )
        row = cursor.fetchone()
        return row["count"] > 0 if row else False
        
    def add_referral_days(self, user_id, days):
        """Add referral days to user's balance."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET referral_days = referral_days + ? WHERE user_id = ?",
            (days, user_id)
        )
        self.conn.commit()
        return True
        
    def set_discount_used(self, user_id):
        """Mark user's discount as used."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET has_used_discount = 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()
        return True

    def get_subscription_stats(self):
        """Get subscription statistics."""
        cursor = self.conn.cursor()
        
        stats = {}
        for tariff_id, tariff in TARIFFS.items():
            cursor.execute(
                "SELECT COUNT(*) as count FROM subscriptions WHERE tariff_id = ? AND status = 'active'",
                (tariff_id,)
            )
            row = cursor.fetchone()
            stats[tariff_id] = {
                "name": tariff["name"],
                "active_count": row["count"] if row else 0,
            }
        
        return stats

    def _parse_speed(self, speed_str):
        """Parse speed string to get numeric value."""
        import re
        match = re.search(r'(\d+)', speed_str)
        if match:
            return float(match.group(1))
        return 50.0  # default

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# Global database instance
db = Database()