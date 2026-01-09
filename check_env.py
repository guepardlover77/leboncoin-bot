#!/usr/bin/env python3
"""
Diagnostic script for Leboncoin Bot environment validation.
Run this on your server to verify the configuration is correct.

Usage: python3 check_env.py
"""

import os
import sys
from pathlib import Path

# Colors for terminal output
class Colors:
    OK = "\033[92m"      # Green
    WARN = "\033[93m"    # Yellow
    FAIL = "\033[91m"    # Red
    BOLD = "\033[1m"
    END = "\033[0m"


def print_ok(msg: str) -> None:
    print(f"{Colors.OK}[OK]{Colors.END} {msg}")


def print_warn(msg: str) -> None:
    print(f"{Colors.WARN}[WARN]{Colors.END} {msg}")


def print_fail(msg: str) -> None:
    print(f"{Colors.FAIL}[FAIL]{Colors.END} {msg}")


def print_header(msg: str) -> None:
    print(f"\n{Colors.BOLD}=== {msg} ==={Colors.END}\n")


def check_python_version() -> bool:
    """Check Python version is 3.8+."""
    version = sys.version_info
    if version >= (3, 8):
        print_ok(f"Python version: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_fail(f"Python {version.major}.{version.minor} detected. Requires 3.8+")
        return False


def check_env_file() -> tuple[bool, dict]:
    """Check .env file exists and contains required variables."""
    env_path = Path(__file__).parent / ".env"
    env_vars = {}

    if not env_path.exists():
        print_fail(f".env file not found at: {env_path}")
        print_warn("Create it from .env.example:")
        print_warn(f"  cp {env_path.parent}/.env.example {env_path}")
        return False, env_vars

    print_ok(f".env file found: {env_path}")

    # Parse .env file
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return True, env_vars


def check_required_env_vars(env_vars: dict) -> bool:
    """Check required environment variables."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    all_ok = True

    for var in required:
        value = env_vars.get(var) or os.environ.get(var)

        if not value:
            print_fail(f"{var}: Missing")
            all_ok = False
        elif value in ("your_bot_token_here", "your_chat_id_here", ""):
            print_fail(f"{var}: Placeholder value (not configured)")
            all_ok = False
        else:
            # Mask sensitive data
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
            print_ok(f"{var}: {masked}")

    # Optional vars
    log_level = env_vars.get("LOG_LEVEL") or os.environ.get("LOG_LEVEL", "INFO")
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    if log_level.upper() in valid_levels:
        print_ok(f"LOG_LEVEL: {log_level}")
    else:
        print_warn(f"LOG_LEVEL: {log_level} (should be one of {valid_levels})")

    return all_ok


def check_directories() -> bool:
    """Check required directories exist and are writable."""
    base_dir = Path(__file__).parent
    directories = {
        "logs": base_dir / "logs",
        "data": base_dir / "data",
        "config": base_dir / "config",
    }

    all_ok = True
    for name, dir_path in directories.items():
        if dir_path.exists():
            # Check if writable
            if os.access(dir_path, os.W_OK):
                print_ok(f"{name}/: exists and writable")
            else:
                print_fail(f"{name}/: exists but NOT writable")
                all_ok = False
        else:
            # Try to create it
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print_ok(f"{name}/: created successfully")
            except OSError as e:
                print_fail(f"{name}/: cannot create - {e}")
                all_ok = False

    return all_ok


def check_config_files() -> bool:
    """Check YAML configuration files exist."""
    config_dir = Path(__file__).parent / "config"
    config_files = ["criteria.yaml", "exclusions.yaml"]

    all_ok = True
    for filename in config_files:
        filepath = config_dir / filename
        if filepath.exists():
            print_ok(f"config/{filename}: found")
        else:
            print_fail(f"config/{filename}: NOT FOUND")
            all_ok = False

    return all_ok


def check_dependencies() -> bool:
    """Check required Python packages are installed."""
    requirements = [
        ("httpx", "httpx"),
        ("beautifulsoup4", "bs4"),
        ("lxml", "lxml"),
        ("python-telegram-bot", "telegram"),
        ("sqlalchemy", "sqlalchemy"),
        ("pyyaml", "yaml"),
        ("python-dotenv", "dotenv"),
    ]

    all_ok = True
    for package_name, import_name in requirements:
        try:
            __import__(import_name)
            print_ok(f"{package_name}: installed")
        except ImportError:
            print_fail(f"{package_name}: NOT INSTALLED")
            all_ok = False

    return all_ok


def check_src_module() -> bool:
    """Check the src module can be imported."""
    src_dir = Path(__file__).parent / "src"
    sys.path.insert(0, str(Path(__file__).parent))

    modules = ["filters", "scraper", "database", "telegram_bot", "main"]
    all_ok = True

    for module_name in modules:
        try:
            __import__(f"src.{module_name}")
            print_ok(f"src.{module_name}: importable")
        except ImportError as e:
            print_fail(f"src.{module_name}: import error - {e}")
            all_ok = False
        except Exception as e:
            print_warn(f"src.{module_name}: {type(e).__name__} - {e}")

    return all_ok


def validate_telegram_token_format(token: str) -> bool:
    """Basic validation of Telegram bot token format."""
    import re
    # Telegram tokens are in format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    pattern = r"^\d+:[A-Za-z0-9_-]+$"
    return bool(re.match(pattern, token))


def validate_chat_id_format(chat_id: str) -> bool:
    """Basic validation of chat ID format."""
    # Chat IDs are integers (can be negative for groups)
    try:
        int(chat_id)
        return True
    except ValueError:
        return False


def main() -> int:
    """Run all diagnostic checks."""
    print(f"\n{Colors.BOLD}Leboncoin Bot - Environment Diagnostic{Colors.END}")
    print("=" * 45)

    results = []

    # 1. Python version
    print_header("Python Version")
    results.append(("Python version", check_python_version()))

    # 2. Environment file
    print_header("Environment Configuration")
    env_exists, env_vars = check_env_file()
    results.append((".env file", env_exists))

    if env_exists:
        results.append(("Required env vars", check_required_env_vars(env_vars)))

        # Validate token format
        token = env_vars.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if token and token not in ("your_bot_token_here", ""):
            if validate_telegram_token_format(token):
                print_ok("TELEGRAM_BOT_TOKEN format: valid")
            else:
                print_warn("TELEGRAM_BOT_TOKEN format: unusual (may still work)")

        # Validate chat ID format
        chat_id = env_vars.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
        if chat_id and chat_id not in ("your_chat_id_here", ""):
            if validate_chat_id_format(chat_id):
                print_ok("TELEGRAM_CHAT_ID format: valid integer")
            else:
                print_fail("TELEGRAM_CHAT_ID format: invalid (must be integer)")

    # 3. Directories
    print_header("Directory Structure")
    results.append(("Directories", check_directories()))

    # 4. Config files
    print_header("Configuration Files")
    results.append(("Config files", check_config_files()))

    # 5. Python dependencies
    print_header("Python Dependencies")
    results.append(("Dependencies", check_dependencies()))

    # 6. Source modules
    print_header("Source Modules")
    results.append(("Source modules", check_src_module()))

    # Summary
    print_header("Summary")
    failed = [name for name, passed in results if not passed]
    passed = [name for name, passed in results if passed]

    print(f"Passed: {len(passed)}/{len(results)}")

    if failed:
        print(f"\n{Colors.FAIL}Failed checks:{Colors.END}")
        for name in failed:
            print(f"  - {name}")
        print(f"\n{Colors.BOLD}Fix the issues above before running the bot.{Colors.END}")
        return 1
    else:
        print(f"\n{Colors.OK}All checks passed!{Colors.END}")
        print(f"\nNext steps:")
        print(f"  1. Run: python3 tests/test_telegram_connection.py")
        print(f"  2. Run: python3 tests/test_lbc_connection.py")
        print(f"  3. Run: python3 dry_run.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
