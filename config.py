# Avava VPN Bot Configuration
import os

# Telegram Bot Token (get from @BotFather on Telegram)
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin User IDs (Telegram user IDs, comma-separated)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",")]

# Database path
DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/avava_vpn.db")

# VPN Configuration (legacy, kept for compatibility)
VPN_CONFIG = {
    "server_address": os.getenv("VPN_SERVER_ADDRESS", "vpn.avava.local"),
    "port": int(os.getenv("VPN_PORT", "1194")),
    "protocol": os.getenv("VPN_PROTOCOL", "udp"),
}

# X-Controller Integration (Subscription Panel)
XCONTROLLER_URL = os.getenv("XCONTROLLER_URL", "http://localhost:8080")
XCONTROLLER_USERNAME = os.getenv("XCONTROLLER_USERNAME", "admin")
XCONTROLLER_PASSWORD = os.getenv("XCONTROLLER_PASSWORD", "")

# YooKassa Payment Integration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY", "")
YOOKASSA_TEST_MODE = os.getenv("YOOKASSA_TEST_MODE", "true").lower() == "true"

# Bot Settings
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@support")
DEFAULT_TRIAL_DAYS = int(os.getenv("DEFAULT_TRIAL_DAYS", "3"))