#!/usr/bin/env python3
"""
Integration test for Leboncoin connectivity.
Checks if the server's IP is blocked by Leboncoin (Error 403).

Usage: python3 tests/test_lbc_connection.py
"""

import sys
import time
import random
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Colors for terminal output
class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_ok(msg: str) -> None:
    print(f"{Colors.OK}[OK]{Colors.END} {msg}")


def print_warn(msg: str) -> None:
    print(f"{Colors.WARN}[WARN]{Colors.END} {msg}")


def print_fail(msg: str) -> None:
    print(f"{Colors.FAIL}[FAIL]{Colors.END} {msg}")


def print_info(msg: str) -> None:
    print(f"{Colors.BOLD}[INFO]{Colors.END} {msg}")


def test_basic_connectivity() -> bool:
    """Test basic internet connectivity."""
    try:
        import httpx

        print_info("Testing basic internet connectivity...")

        client = httpx.Client(timeout=10.0)
        response = client.get("https://www.google.com")
        client.close()

        if response.status_code == 200:
            print_ok("Internet connectivity OK")
            return True
        else:
            print_warn(f"Unexpected status: {response.status_code}")
            return True  # Still has connectivity

    except Exception as e:
        print_fail(f"No internet connection: {e}")
        return False


def test_leboncoin_homepage() -> tuple[bool, int]:
    """
    Test access to Leboncoin homepage.

    Returns:
        (success, status_code)
    """
    try:
        import httpx

        print_info("Testing Leboncoin homepage access...")

        # Use realistic headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)

        # Small delay to be polite
        time.sleep(random.uniform(1, 2))

        response = client.get("https://www.leboncoin.fr")
        client.close()

        status = response.status_code

        if status == 200:
            print_ok(f"Leboncoin homepage: {status} OK")
            return True, status
        elif status == 403:
            print_fail(f"Leboncoin homepage: {status} FORBIDDEN")
            print_warn("Your IP may be blocked by Leboncoin")
            return False, status
        elif status == 429:
            print_warn(f"Leboncoin homepage: {status} RATE LIMITED")
            print_info("Too many requests - wait and try again")
            return False, status
        else:
            print_warn(f"Leboncoin homepage: {status} (unexpected)")
            return False, status

    except Exception as e:
        print_fail(f"Error accessing Leboncoin: {e}")
        return False, 0


def test_leboncoin_search() -> tuple[bool, int]:
    """
    Test access to Leboncoin search page.

    Returns:
        (success, status_code)
    """
    try:
        import httpx

        print_info("Testing Leboncoin search page...")

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.leboncoin.fr/",
        }

        client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)

        # Test a simple car search
        search_url = (
            "https://www.leboncoin.fr/recherche?"
            "category=2&"
            "brand=mazda&"
            "model=2&"
            "price=0-3000&"
            "fuel=1&"
            "gearbox=1&"
            "sort=time&"
            "order=desc"
        )

        # Delay to be polite
        time.sleep(random.uniform(2, 4))

        response = client.get(search_url)
        client.close()

        status = response.status_code

        if status == 200:
            print_ok(f"Leboncoin search: {status} OK")

            # Check for actual content
            if "__NEXT_DATA__" in response.text:
                print_ok("Search page contains __NEXT_DATA__ (JSON data)")
            else:
                print_warn("Search page missing __NEXT_DATA__ (may need parsing update)")

            return True, status

        elif status == 403:
            print_fail(f"Leboncoin search: {status} FORBIDDEN")
            return False, status
        elif status == 429:
            print_warn(f"Leboncoin search: {status} RATE LIMITED")
            return False, status
        else:
            print_warn(f"Leboncoin search: {status} (unexpected)")
            return False, status

    except Exception as e:
        print_fail(f"Error accessing search: {e}")
        return False, 0


def test_scraper_module() -> bool:
    """Test that the scraper module works."""
    try:
        print_info("Testing scraper module...")

        from src.scraper import LeboncoinScraper

        scraper = LeboncoinScraper(delay_min=1.0, delay_max=2.0)

        # Test parameter building
        params = scraper._build_search_params(
            brand="mazda",
            model="2",
            max_price=3000,
            fuel="essence",
        )

        if params.get("brand") == "mazda" and params.get("fuel") == "1":
            print_ok("Scraper parameter building works")
            return True
        else:
            print_fail("Scraper parameters incorrect")
            return False

    except ImportError as e:
        print_fail(f"Cannot import scraper: {e}")
        return False
    except Exception as e:
        print_fail(f"Scraper error: {e}")
        return False


def test_live_search() -> bool:
    """
    Test an actual search (with real network request).
    This is the most complete test but takes time.
    """
    try:
        print_info("Testing live search (this may take 10-15 seconds)...")

        from src.scraper import LeboncoinScraper

        # Use shorter delays for testing
        scraper = LeboncoinScraper(delay_min=2.0, delay_max=4.0)

        listings = scraper.search_cars(
            brand="mazda",
            model="2",
            max_price=5000,  # Higher limit to ensure results
            max_km=200000,
            min_year=2005,
            max_results=5,  # Limit results
        )

        scraper.close()

        if listings:
            print_ok(f"Live search returned {len(listings)} listings")

            # Show sample listing
            first = listings[0]
            print_info(f"  Sample: {first.title}")
            if first.price:
                print_info(f"    Price: {first.price}")
            if first.mileage:
                print_info(f"    Km: {first.mileage}")
            if first.year:
                print_info(f"    Year: {first.year}")

            return True
        else:
            print_warn("Live search returned no listings")
            print_info("This could mean:")
            print_info("  - No listings match the criteria")
            print_info("  - IP might be soft-blocked")
            print_info("  - Site structure changed")
            return False

    except Exception as e:
        print_fail(f"Live search error: {e}")
        return False


def diagnose_403_error():
    """Provide diagnosis for 403 errors."""
    print(f"\n{Colors.BOLD}403 Forbidden - Diagnosis{Colors.END}")
    print("=" * 45)
    print("""
Possible causes for 403 error:

1. **IP Blocked**: Your server's IP may be blocked by Leboncoin.
   - Try from a different IP/VPN
   - Wait 24-48 hours for temporary blocks to clear

2. **Rate Limiting**: Too many requests too quickly.
   - Increase delays between requests
   - The bot uses 5-10 second delays by default

3. **Missing Headers**: Bot detection triggered.
   - The scraper uses realistic browser headers
   - This is usually not the issue

4. **Cloudflare Protection**: Site may have enhanced protection.
   - Try at different times of day
   - Some server IPs are more trusted

Recommended Actions:
  1. Wait 1 hour and try again
  2. Check if leboncoin.fr works in a browser on this server
  3. Try using a VPN or different server
  4. Contact Leboncoin if you believe blocking is in error
""")


def main() -> int:
    """Run Leboncoin connection tests."""
    print(f"\n{Colors.BOLD}Leboncoin Connection Test{Colors.END}")
    print("=" * 45)
    print()

    results = []

    # Test 1: Basic connectivity
    print(f"\n{Colors.BOLD}Test 1: Basic Internet Connectivity{Colors.END}")
    result = test_basic_connectivity()
    results.append(("Internet", result))

    if not result:
        print_fail("Cannot proceed without internet connection")
        return 1

    # Test 2: Leboncoin homepage
    print(f"\n{Colors.BOLD}Test 2: Leboncoin Homepage{Colors.END}")
    result, status = test_leboncoin_homepage()
    results.append(("Homepage", result))

    if status == 403:
        diagnose_403_error()
        return 1

    # Test 3: Leboncoin search page
    print(f"\n{Colors.BOLD}Test 3: Leboncoin Search Page{Colors.END}")
    result, status = test_leboncoin_search()
    results.append(("Search Page", result))

    if status == 403:
        diagnose_403_error()
        return 1

    # Test 4: Scraper module
    print(f"\n{Colors.BOLD}Test 4: Scraper Module{Colors.END}")
    result = test_scraper_module()
    results.append(("Scraper Module", result))

    # Test 5: Live search (optional but recommended)
    print(f"\n{Colors.BOLD}Test 5: Live Search{Colors.END}")
    result = test_live_search()
    results.append(("Live Search", result))

    # Summary
    print(f"\n{Colors.BOLD}Summary{Colors.END}")
    print("=" * 45)

    all_passed = True
    for name, passed in results:
        status = f"{Colors.OK}PASS{Colors.END}" if passed else f"{Colors.FAIL}FAIL{Colors.END}"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n{Colors.OK}All Leboncoin connectivity tests passed!{Colors.END}")
        print("\nYour server can successfully scrape Leboncoin.")
        print("\nNext steps:")
        print("  1. Run: python3 dry_run.py")
        print("  2. Start the bot: python3 -m src.main")
        return 0
    else:
        print(f"\n{Colors.WARN}Some tests failed.{Colors.END}")
        print("\nThe bot may still work, but check the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
