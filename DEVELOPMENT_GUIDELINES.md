# Avava VPN Bot — Development Guidelines (The Talmud)

> **This document is mandatory reading for anyone contributing to this project.**
> If you're reading this, you're already ahead of 90% of contributors who just push code.

---

## 1. Linter & Code Quality

### The Only Linter: **Ruff**

```bash
# Check (run before every commit)
python -m ruff check .

# Auto-fix what can be fixed
python -m ruff check --fix .

# Format (run before every commit)
python -m ruff format .
```

### Ruff Configuration

The project uses `pyproject.toml` for Ruff config. **Do not modify it without discussion.**

Key rules enforced:
- **I001** — Import sorting (standard library → third-party → local)
- **BLE001** — No blind `except Exception:` — catch specific exceptions
- **PLW0602** — Global variable usage warnings
- **SIM117** — Combine nested `with` statements
- **F401/F811/F821** — Unused/redefined/undefined imports
- **All pyflakes/pycodestyle/pyflakes rules** — via Ruff's built-in rules

### When to Suppress (and ONLY when)

| Rule | When to `# noqa` | Example |
|------|------------------|---------|
| `BLE001` | Graceful degradation in handlers — catching all errors to show user-friendly message and log details | `except Exception as e:  # noqa: BLE001` |
| `PLW0602` | Module-level caches/state that are intentionally mutated via `global` | `_cache: dict = {}  # noqa: PLW0602` |
| Others | **Almost never**. Fix the code instead. | — |

**Rule of thumb:** If you're adding `# noqa`, add a comment explaining WHY. Future you will thank present you.

---

## 2. Testing — Not Optional

### Write Tests For:
- ✅ All new handlers
- ✅ All new service functions (subscription_service, xcontroller_client, yookassa, database)
- ✅ All new utility functions
- ✅ All bug fixes (regression tests)
- ✅ Edge cases: empty DB, network failures, invalid input, concurrent access

### Test Structure

```
tests/
├── test_admin_handlers.py
├── test_database.py
├── test_handlers.py
├── test_keyboards.py
├── test_monitoring.py
├── test_subscription_service.py
├── test_subscription_service_more.py
├── test_subscriptions_handlers.py
├── test_utils.py
├── test_xcontroller_client.py
└── test_yookassa.py
```

### Run Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_subscription_service.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Test Standards

- **Mock external dependencies** (X-Controller, YooKassa, Telegram API)
- **Use fixtures** for common setup (see `conftest.py` if exists)
- **Test both success and failure paths**
- **Name tests clearly**: `test_<function>_<scenario>_<expected>`
- **No flaky tests** — if it's flaky, fix it or delete it

---

## 3. Code Style & Architecture

### Import Order (enforced by Ruff I001)

```python
# 1. Standard library
import logging
import uuid
from datetime import datetime

# 2. Third-party
import requests
from telegram import Update, InlineKeyboardMarkup

# 3. Local (absolute imports from project root)
import app_context
import config
from database import TARIFFS, db
from handlers.subscriptions import create_paid_subscription
from utils import back_btn, btn
```

### Type Hints

**Required** for:
- All function signatures (args + return)
- Public module-level variables
- Class attributes

```python
# Good
async def handle_subscribe(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    tariff_id: str
) -> None: ...

# Bad
async def handle_subscribe(update, context, user_id, tariff_id): ...
```

### Async/Await

- All handlers are `async def`
- Use `await` for all I/O (DB, HTTP, Telegram API)
- Don't mix sync/async — if a function does I/O, make it async

### Error Handling Pattern

```python
# Standard pattern for handlers
try:
    result = await risky_operation()
except SpecificException as e:
    logger.error("Operation failed: %s", e)
    await query.edit_message_text("❌ User-friendly message")
    return
except (NetworkError, TimeoutError) as e:  # Group related
    logger.warning("Transient error: %s", e)
    await query.edit_message_text("⏳ Try again later")
    return
```

---

## 4. Protected Modules — DO NOT BREAK

These modules are **battle-tested, production-hardened, and considered "done"**.
Changes require **explicit approval** and **extensive testing**.

| Module | Why It's Protected | What NOT To Do |
|--------|-------------------|----------------|
| `handlers/payments.py` | Handles real money, YooKassa integration, refunds, extensions, tariff changes | Change payment flow, modify order_id format, touch refund logic, alter capture logic |
| `handlers/subscriptions.py` | Core subscription lifecycle (create, extend, change, cancel) | Modify `create_paid_subscription`, `handle_free_subscription`, `handle_tariff_change` |
| `subscription_service.py` | Business logic layer between bot and X-Controller | Change health check logic, panel selection, subscription creation flow |
| `yookassa.py` | Payment gateway wrapper — PCI-adjacent | Modify `create_payment`, `check_payment`, `capture_payment`, `create_refund`, DB schema |
| `xcontroller_client.py` | X-Controller API client — all panel communication | Change `_make_request`, auth, endpoint paths, error classes |
| `database.py` | SQLite schema, migrations, all queries | Modify table schemas, change migration logic, alter `TARIFFS` structure |
| `handlers/admin.py` | Admin panel — sensitive operations | Change admin checks, user management, stats calculation |
| `keyboards.py` | All UI keyboards — consistent UX | Change button layouts, callback data formats, navigation flow |
| `utils.py` | Shared utilities (channel check, date formatting, referral logic) | Modify `check_channel_subscription`, `safe_date_format`, referral logic |

### If You MUST Touch Protected Code

1. **Open an issue first** — explain what and why
2. **Write tests BEFORE changing** — cover existing behavior
3. **Make minimal changes** — surgical, not rewrite
4. **Get code review** — from someone who knows the module
5. **Deploy to staging first** — test with real payments (test mode)

---

## 5. Git Workflow

### Branch Naming

```
feature/<short-description>     # New feature
fix/<short-description>         # Bug fix
refactor/<short-description>    # Code improvement (no behavior change)
docs/<short-description>        # Documentation only
```

### Commit Messages

```
<type>(<scope>): <short summary>

<body if needed>

Fixes #<issue-number>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`

### Before Pushing

```bash
# 1. Format
python -m ruff format .

# 2. Lint
python -m ruff check .

# 3. Test
python -m pytest tests/ -v

# 4. Only then push
```

---

## 6. Configuration & Secrets

### Never Commit

- `.env` files
- API keys, tokens, passwords
- Database files (`*.db`, `*.sqlite`)
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`

### Config Pattern

All config in `config.py` — loaded from environment variables.
Use `config.SOME_SETTING` everywhere. **No hardcoded values.**

---

## 7. Database Migrations

- Migrations live in `database.py` in `Database.__init__`
- **Never** modify existing migrations — add new ones
- Test migrations on a copy of production data
- Backup before running on production

---

## 8. Adding New Features

### Checklist

- [ ] Issue created with clear requirements
- [ ] Tests written first (TDD preferred)
- [ ] Handler added to `bot.py` routing
- [ ] Keyboard updates in `keyboards.py` if UI changes
- [ ] Admin commands protected with `is_admin()`
- [ ] User-facing text in Russian (project language)
- [ ] Logging added for important operations
- [ ] Error handling follows project patterns
- [ ] Ruff passes, tests pass
- [ ] Documentation updated if needed

---

## 9. Logging

```python
# Module logger (top of file)
logger = logging.getLogger(__name__)

# Levels
logger.debug("Detailed debug info")      # Development only
logger.info("Important lifecycle event") # Payment created, sub extended
logger.warning("Recoverable issue")      # Retryable, non-critical
logger.error("Failed operation")         # User-facing failure
logger.exception("Unexpected error")     # With traceback
```

---

## 10. Telegram Bot Specifics

### Callback Data Format

```
<action>_<entity>_<id>[_<extra>]
```

Examples:
- `subscribe_trial`
- `check_payment_avava_123_trial_a1b2c3d4`
- `extend_42`
- `change_tariff_42_premium`
- `admin_ban_123456`

### State Management

Use `context.user_data` for transient state:
```python
context.user_data["state"] = STATE_PAYMENT_PENDING
context.user_data["pending_order_id"] = order_id
```

Clear state after completion.

---

## 11. Performance

- **Cache panel statuses** (10s TTL in monitoring)
- **Batch DB queries** — avoid N+1
- **Reuse HTTP sessions** — `requests.Session()` in XControllerClient
- **Don't block event loop** — all I/O must be async

---

## 12. Security

- **Validate all user input** — tariff IDs, subscription IDs, user IDs
- **Check ownership** — `subscription["user_id"] == user_id` before any action
- **Admin-only endpoints** — `@is_admin` decorator or explicit check
- **No SQL injection** — use parameterized queries (already enforced)
- **Payment IDs** — never log full payment details, only IDs

---

## 13. Deployment

```bash
# Build
docker compose build

# Run (production)
docker compose up -d

# Logs
docker compose logs -f bot

# Migrations run automatically on container start
```

---

## 14. Quick Reference: File Purposes

| File | Purpose |
|------|---------|
| `bot.py` | Entry point, app initialization, handler routing |
| `config.py` | All configuration from env vars |
| `database.py` | SQLite models, queries, migrations, TARIFFS |
| `app_context.py` | Global singletons (db, yookassa, xcontroller, subscription_manager) |
| `subscription_service.py` | Business logic: create/extend/change/cancel subscriptions |
| `xcontroller_client.py` | X-Controller REST API client |
| `yookassa.py` | YooKassa payment gateway + payment storage |
| `handlers/*.py` | Telegram callback/command handlers |
| `keyboards.py` | All InlineKeyboardMarkup builders |
| `utils.py` | Shared helpers (channel check, dates, referrals) |

---

## 15. Final Words

> **"Code is read more than written. Write for the next person who has to debug this at 3 AM."**

- If you're unsure — **ask**. Better a stupid question than a broken payment flow.
- If you see something weird — **document it** or **fix it**.
- If you break a protected module — **you own the fix**.

**Welcome to the project. Don't make me regret adding you.**

---

*Last updated: 2026-08-19*
*Version: 1.0*