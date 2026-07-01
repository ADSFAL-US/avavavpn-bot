"""Shared application context for handlers.

These globals are initialized in bot.py at startup and
imported by handler modules that need access to runtime objects.
"""
import logging

# YooKassa payment client (initialized in bot.py)
yookassa = None

# Payment storage (initialized in bot.py)
payment_storage = None

# X-Controller client (initialized in bot.py)
xcontroller = None

# Subscription manager (initialized in bot.py)
subscription_manager = None

logger = logging.getLogger(__name__)
