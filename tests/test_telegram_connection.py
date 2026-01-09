#!/usr/bin/env python3
"""
Integration test for Telegram bot connectivity.
Sends a test message to verify the bot can communicate.

This is the FIRST thing to run after creating the .env on the server.

Usage: python3 tests/test_telegram_connection.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# Colors for terminal output
class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_ok(msg: str) -> None:
    print(f"{Colors.OK}[OK]{Colors.END} {msg}")


def print_fail(msg: str) -> None:
    print(f"{Colors.FAIL}[FAIL]{Colors.END} {msg}")


def print_info(msg: str) -> None:
    print(f"{Colors.BOLD}[INFO]{Colors.END} {msg}")


async def test_telegram_connection() -> bool:
    """
    Test Telegram bot connection by sending a test message.

    Returns:
        True if successful, False otherwise.
    """
    # Check environment variables
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        print_fail("TELEGRAM_BOT_TOKEN not found in environment")
        print_info("Make sure .env file exists and contains TELEGRAM_BOT_TOKEN")
        return False

    if not chat_id:
        print_fail("TELEGRAM_CHAT_ID not found in environment")
        print_info("Make sure .env file exists and contains TELEGRAM_CHAT_ID")
        return False

    print_info(f"Token: {token[:10]}...{token[-5:]}")
    print_info(f"Chat ID: {chat_id}")

    try:
        from telegram import Bot
        from telegram.error import TelegramError
    except ImportError:
        print_fail("python-telegram-bot not installed")
        print_info("Run: pip install python-telegram-bot")
        return False

    print_info("Attempting to connect to Telegram API...")

    try:
        bot = Bot(token=token)

        # Test 1: Get bot info
        me = await bot.get_me()
        print_ok(f"Bot connected: @{me.username} ({me.first_name})")

        # Test 2: Send test message
        test_message = (
            " **Leboncoin Bot - Test Message**\n\n"
            "If you see this message, the Telegram connection is working!\n\n"
            "Sent from: test_telegram_connection.py"
        )

        message = await bot.send_message(
            chat_id=chat_id,
            text=test_message,
            parse_mode="Markdown",
        )
        print_ok(f"Test message sent successfully (message_id: {message.message_id})")

        # Test 3: Verify chat access
        try:
            chat = await bot.get_chat(chat_id)
            chat_type = chat.type
            chat_title = getattr(chat, 'title', None) or getattr(chat, 'username', None) or "Private"
            print_ok(f"Chat verified: {chat_title} (type: {chat_type})")
        except TelegramError as e:
            print_fail(f"Could not get chat info: {e}")
            # This is not critical, message was sent

        return True

    except TelegramError as e:
        print_fail(f"Telegram API error: {e}")

        # Provide helpful error messages
        error_str = str(e).lower()
        if "unauthorized" in error_str or "401" in error_str:
            print_info("The bot token appears to be invalid.")
            print_info("Get a new token from @BotFather on Telegram.")
        elif "chat not found" in error_str or "400" in error_str:
            print_info("The chat ID appears to be invalid.")
            print_info("To get your chat ID:")
            print_info("  1. Send a message to @userinfobot")
            print_info("  2. It will reply with your user ID")
            print_info("  3. Use that number as TELEGRAM_CHAT_ID")
        elif "forbidden" in error_str or "403" in error_str:
            print_info("The bot cannot send messages to this chat.")
            print_info("Make sure you have started a conversation with the bot")
            print_info("by sending /start to it on Telegram.")

        return False

    except Exception as e:
        print_fail(f"Unexpected error: {type(e).__name__}: {e}")
        return False


async def test_bot_commands() -> bool:
    """
    Test that bot command handlers can be registered.
    """
    print_info("Testing bot command registration...")

    try:
        from telegram.ext import Application, CommandHandler

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return False

        app = Application.builder().token(token).build()

        # Test adding a command handler
        async def dummy_handler(update, context):
            pass

        app.add_handler(CommandHandler("test", dummy_handler))
        print_ok("Command handlers can be registered")

        return True

    except Exception as e:
        print_fail(f"Error testing command handlers: {e}")
        return False


def main() -> int:
    """Run Telegram connection tests."""
    print(f"\n{Colors.BOLD}Telegram Connection Test{Colors.END}")
    print("=" * 40)
    print()

    # Run async tests
    results = []

    # Test 1: Basic connection and message
    print(f"\n{Colors.BOLD}Test 1: Connection & Send Message{Colors.END}")
    result = asyncio.run(test_telegram_connection())
    results.append(("Connection & Message", result))

    # Test 2: Command handlers
    print(f"\n{Colors.BOLD}Test 2: Command Handler Registration{Colors.END}")
    result = asyncio.run(test_bot_commands())
    results.append(("Command Handlers", result))

    # Summary
    print(f"\n{Colors.BOLD}Summary{Colors.END}")
    print("=" * 40)

    all_passed = True
    for name, passed in results:
        status = f"{Colors.OK}PASS{Colors.END}" if passed else f"{Colors.FAIL}FAIL{Colors.END}"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n{Colors.OK}All Telegram tests passed!{Colors.END}")
        print("\nNext steps:")
        print("  1. Run: python3 tests/test_lbc_connection.py")
        print("  2. Run: python3 dry_run.py")
        return 0
    else:
        print(f"\n{Colors.FAIL}Some tests failed.{Colors.END}")
        print("\nTroubleshooting:")
        print("  1. Check your .env file has correct values")
        print("  2. Make sure you've started the bot on Telegram (/start)")
        print("  3. Verify your internet connection")
        return 1


if __name__ == "__main__":
    sys.exit(main())
