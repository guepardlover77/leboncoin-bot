#!/usr/bin/env python3
"""
Dry Run Script for Leboncoin Bot.

Runs a single search cycle and prints results to stdout without:
- Saving to database
- Sending Telegram notifications
- Waiting for the next cycle

Useful to see what the bot would find without waiting 30 minutes.

Usage: python3 dry_run.py [--model MODEL] [--limit N] [--verbose]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables (not strictly needed for dry run)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


# Colors for terminal output
class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    END = "\033[0m"


def print_header(msg: str) -> None:
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{msg}{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.END}\n")


def print_listing(listing, score_result, index: int) -> None:
    """Print a single listing with formatting."""
    priority_colors = {
        "high": Colors.OK,
        "medium": Colors.WARN,
        "low": Colors.DIM,
    }
    priority_emoji = {
        "high": "",
        "medium": "",
        "low": "",
    }

    color = priority_colors.get(score_result.priority, "")
    emoji = priority_emoji.get(score_result.priority, "")

    print(f"{color}[{index}] {emoji} {listing.title}{Colors.END}")
    print(f"    Score: {score_result.total_score} ({score_result.priority.upper()})")
    print(f"    Price: {listing.price or 'N/A'}  |  "
          f"Km: {listing.mileage or 'N/A'}  |  "
          f"Year: {listing.year or 'N/A'}")
    print(f"    Fuel: {listing.fuel or 'N/A'}  |  "
          f"Gearbox: {listing.gearbox or 'N/A'}")
    if listing.location:
        print(f"    Location: {listing.location}")
    print(f"    URL: {listing.url}")

    if score_result.bonuses:
        print(f"    {Colors.OK}Bonuses: {', '.join(score_result.bonuses)}{Colors.END}")
    if score_result.penalties:
        print(f"    {Colors.FAIL}Penalties: {', '.join(score_result.penalties)}{Colors.END}")
    if score_result.warnings:
        print(f"    {Colors.WARN}Warnings: {', '.join(score_result.warnings)}{Colors.END}")
    print()


def dry_run(
    model_filter: str = None,
    limit: int = 10,
    verbose: bool = False,
) -> int:
    """
    Run a single search cycle without saving or notifying.

    Args:
        model_filter: Optional model name to filter (e.g., "mazda_2")
        limit: Maximum number of listings to display per model
        verbose: Show more details

    Returns:
        Exit code (0 = success)
    """
    try:
        from src.scraper import LeboncoinScraper
        from src.filters import CarFilter
    except ImportError as e:
        print(f"{Colors.FAIL}Import error: {e}{Colors.END}")
        print("Make sure you're running from the leboncoin-bot directory.")
        return 1

    print_header("Leboncoin Bot - Dry Run")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Model filter: {model_filter or 'all'}")
    print(f"Max results per model: {limit}")

    # Initialize components
    config_dir = Path(__file__).parent / "config"
    car_filter = CarFilter(config_dir=str(config_dir))

    # Get models from configuration
    models = car_filter.get_model_configs()

    if not models:
        print(f"{Colors.FAIL}No models configured in criteria.yaml{Colors.END}")
        return 1

    # Filter models if specified
    if model_filter:
        model_filter_lower = model_filter.lower().replace("_", " ").replace("-", " ")
        models = [
            m for m in models
            if model_filter_lower in m.get("name", "").lower()
            or model_filter_lower in f"{m.get('brand', '')} {m.get('model', '')}".lower()
        ]
        if not models:
            print(f"{Colors.FAIL}No models matching '{model_filter}'{Colors.END}")
            print("Available models:")
            for m in car_filter.get_model_configs():
                print(f"  - {m.get('name', 'Unknown')}")
            return 1

    print(f"\nSearching {len(models)} model(s)...")

    # Create scraper with shorter delays for testing
    scraper = LeboncoinScraper(delay_min=3.0, delay_max=6.0)

    # Get general criteria
    general = car_filter.criteria.get("general", {})
    max_price = general.get("max_price", 3000)
    max_km = general.get("max_km", 150000)
    min_year = general.get("min_year", 2008)
    fuel = general.get("fuel", "essence")
    gearbox = general.get("gearbox", "manuelle")

    total_found = 0
    total_high = 0
    total_medium = 0
    total_excluded = 0

    try:
        for model_config in models:
            model_name = model_config.get("name", "Unknown")
            brand = model_config.get("brand", "")
            model = model_config.get("model", "")

            print_header(f"Searching: {model_name}")

            if verbose:
                print(f"Brand: {brand}, Model: {model}")
                print(f"Max price: {max_price}, Max km: {max_km}, Min year: {min_year}")
                print()

            # Search
            try:
                listings = scraper.search_cars(
                    brand=brand,
                    model=model,
                    max_price=max_price,
                    max_km=max_km,
                    min_year=min_year,
                    fuel=fuel,
                    gearbox=gearbox,
                    max_results=limit * 2,  # Get extra for filtering
                )
            except Exception as e:
                print(f"{Colors.FAIL}Search error: {e}{Colors.END}")
                continue

            if not listings:
                print(f"{Colors.WARN}No listings found{Colors.END}")
                continue

            print(f"Found {len(listings)} raw listings")
            print()

            # Evaluate each listing
            displayed = 0
            for listing in listings:
                # Score the listing
                score_result = car_filter.evaluate(
                    listing_id=listing.listing_id,
                    title=listing.title,
                    description=listing.description or "",
                    price=listing.price,
                    mileage=listing.mileage,
                    year=listing.year,
                    fuel=listing.fuel,
                    gearbox=listing.gearbox,
                    brand=listing.brand,
                    model=listing.model,
                    engine=listing.engine,
                )

                if score_result.excluded:
                    total_excluded += 1
                    if verbose:
                        print(f"{Colors.DIM}EXCLUDED: {listing.title}")
                        print(f"  Reason: {score_result.exclusion_reason}{Colors.END}")
                    continue

                total_found += 1
                if score_result.priority == "high":
                    total_high += 1
                elif score_result.priority == "medium":
                    total_medium += 1

                # Display listing
                if displayed < limit:
                    print_listing(listing, score_result, displayed + 1)
                    displayed += 1

            if displayed == 0:
                print(f"{Colors.WARN}All listings were excluded or filtered{Colors.END}")

    finally:
        scraper.close()

    # Summary
    print_header("Summary")
    print(f"Total listings found (after filtering): {total_found}")
    print(f"  - {Colors.OK}High priority: {total_high}{Colors.END}")
    print(f"  - {Colors.WARN}Medium priority: {total_medium}{Colors.END}")
    print(f"  - Low priority: {total_found - total_high - total_medium}")
    print(f"  - {Colors.DIM}Excluded: {total_excluded}{Colors.END}")
    print()

    if total_high > 0:
        print(f"{Colors.OK}High priority listings would trigger urgent notifications!{Colors.END}")
    elif total_found > 0:
        print(f"{Colors.WARN}No high priority listings found, but {total_found} would be notified.{Colors.END}")
    else:
        print(f"{Colors.WARN}No listings matched your criteria.{Colors.END}")
        print("Consider adjusting your criteria in config/criteria.yaml")

    return 0


def main():
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description="Dry run the Leboncoin bot without saving or notifying."
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        help="Filter to specific model (e.g., 'mazda_2', 'honda jazz')"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Maximum listings to display per model (default: 10)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show more details including excluded listings"
    )

    args = parser.parse_args()

    return dry_run(
        model_filter=args.model,
        limit=args.limit,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
