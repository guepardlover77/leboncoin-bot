#!/usr/bin/env python3
"""
Unit tests for Leboncoin HTML/JSON parsing.
Ensures that recent site changes haven't broken the scraper.

Run with: python -m pytest tests/test_parser.py -v
Or:       python tests/test_parser.py
"""

import sys
import json
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scraper import LeboncoinScraper, CarListing


# Sample JSON data structure from Leboncoin __NEXT_DATA__
SAMPLE_AD_JSON = {
    "list_id": 2345678901,
    "subject": "Mazda 2 1.3 MZR 75ch Elegance 5p",
    "price": [2800],
    "url": "https://www.leboncoin.fr/ad/voitures/2345678901.htm",
    "body": "Mazda 2 en excellent etat. Distribution par chaine. Carnet d'entretien a jour.",
    "attributes": [
        {"key": "mileage", "value": "95 000 km"},
        {"key": "regdate", "value": "2012"},
        {"key": "fuel", "value": "Essence"},
        {"key": "gearbox", "value": "Manuelle"},
        {"key": "vehicle_engine", "value": "1.3 MZR 75ch"},
    ],
    "location": {
        "city": "Paris",
        "zipcode": "75000",
        "department_name": "Paris",
    },
    "images": {
        "urls": [
            "https://img.leboncoin.fr/ad-image/12345.jpg",
            "https://img.leboncoin.fr/ad-image/12346.jpg",
        ],
        "small_url": "https://img.leboncoin.fr/ad-small/12345.jpg",
    },
}

SAMPLE_NEXT_DATA = {
    "props": {
        "pageProps": {
            "searchData": {
                "ads": [SAMPLE_AD_JSON],
                "total": 1,
            }
        }
    }
}

# Minimal HTML structure for fallback parsing test
SAMPLE_HTML_FALLBACK = '''
<!DOCTYPE html>
<html>
<head><title>Search Results</title></head>
<body>
    <a href="/ad/voitures/9876543210.htm" data-test-id="ad">
        <h2 class="styles_title">Honda Jazz 1.4 i-VTEC</h2>
        <span class="styles_price">2 500 </span>
    </a>
    <a href="/ad/voitures/9876543211.htm" data-test-id="ad">
        <h2 class="styles_title">Suzuki Swift 1.2</h2>
        <span class="styles_price">2 900 </span>
    </a>
</body>
</html>
'''


class TestCarListing(unittest.TestCase):
    """Test CarListing dataclass."""

    def test_to_dict(self):
        """Test CarListing.to_dict() method."""
        listing = CarListing(
            listing_id="123456",
            url="https://www.leboncoin.fr/ad/voitures/123456.htm",
            title="Test Car",
            price=2500,
            mileage=100000,
            year=2012,
            fuel="Essence",
            gearbox="Manuelle",
            brand="mazda",
            model="2",
            engine="1.3 MZR",
            location="Paris",
            description="Test description",
            image_url="https://img.example.com/car.jpg",
        )

        d = listing.to_dict()

        self.assertEqual(d["listing_id"], "123456")
        self.assertEqual(d["title"], "Test Car")
        self.assertEqual(d["price"], 2500)
        self.assertEqual(d["mileage"], 100000)
        self.assertEqual(d["year"], 2012)

    def test_default_values(self):
        """Test CarListing with minimal fields."""
        listing = CarListing(
            listing_id="123",
            url="https://example.com",
            title="Test",
        )

        self.assertIsNone(listing.price)
        self.assertIsNone(listing.mileage)
        self.assertIsNone(listing.year)
        self.assertEqual(listing.raw_data, {})


class TestScraperJsonParsing(unittest.TestCase):
    """Test JSON parsing from __NEXT_DATA__."""

    def setUp(self):
        self.scraper = LeboncoinScraper()

    def test_parse_ad_json_complete(self):
        """Test parsing a complete ad JSON object."""
        listing = self.scraper._parse_ad_json(SAMPLE_AD_JSON, "mazda", "2")

        self.assertIsNotNone(listing)
        self.assertEqual(listing.listing_id, "2345678901")
        self.assertEqual(listing.title, "Mazda 2 1.3 MZR 75ch Elegance 5p")
        self.assertEqual(listing.price, 2800)
        self.assertEqual(listing.mileage, 95000)
        self.assertEqual(listing.year, 2012)
        self.assertEqual(listing.fuel, "Essence")
        self.assertEqual(listing.gearbox, "Manuelle")
        self.assertEqual(listing.engine, "1.3 MZR 75ch")
        self.assertEqual(listing.location, "Paris")
        self.assertEqual(listing.brand, "mazda")
        self.assertEqual(listing.model, "2")

    def test_parse_ad_json_mileage_formats(self):
        """Test parsing various mileage formats."""
        test_cases = [
            ({"mileage": "95 000 km"}, 95000),
            ({"mileage": "95000 km"}, 95000),
            ({"mileage": "120000"}, 120000),
            ({"mileage": "42 000"}, 42000),
        ]

        for attrs, expected_mileage in test_cases:
            ad = {
                "list_id": 123,
                "subject": "Test Car",
                "attributes": [{"key": k, "value": v} for k, v in attrs.items()],
            }
            listing = self.scraper._parse_ad_json(ad, "test", "car")
            self.assertEqual(
                listing.mileage,
                expected_mileage,
                f"Failed for mileage: {attrs['mileage']}"
            )

    def test_parse_ad_json_year_extraction(self):
        """Test year extraction from regdate."""
        test_cases = [
            ({"regdate": "2012"}, 2012),
            ({"regdate": "01/2015"}, 2015),
            ({"regdate": "2018-06"}, 2018),
        ]

        for attrs, expected_year in test_cases:
            ad = {
                "list_id": 123,
                "subject": "Test Car",
                "attributes": [{"key": k, "value": v} for k, v in attrs.items()],
            }
            listing = self.scraper._parse_ad_json(ad, "test", "car")
            self.assertEqual(
                listing.year,
                expected_year,
                f"Failed for regdate: {attrs['regdate']}"
            )

    def test_parse_ad_json_price_formats(self):
        """Test price extraction (list vs direct value)."""
        # Price as list
        ad1 = {
            "list_id": 123,
            "subject": "Test",
            "price": [2500],
            "attributes": [],
        }
        listing1 = self.scraper._parse_ad_json(ad1, "test", "car")
        self.assertEqual(listing1.price, 2500)

        # Price as direct value
        ad2 = {
            "list_id": 124,
            "subject": "Test",
            "price": 3000,
            "attributes": [],
        }
        listing2 = self.scraper._parse_ad_json(ad2, "test", "car")
        self.assertEqual(listing2.price, 3000)

    def test_parse_ad_json_missing_fields(self):
        """Test parsing with missing optional fields."""
        minimal_ad = {
            "list_id": 999,
            "subject": "Minimal Car",
            "attributes": [],
        }
        listing = self.scraper._parse_ad_json(minimal_ad, "test", "car")

        self.assertIsNotNone(listing)
        self.assertEqual(listing.listing_id, "999")
        self.assertEqual(listing.title, "Minimal Car")
        self.assertIsNone(listing.price)
        self.assertIsNone(listing.mileage)
        self.assertIsNone(listing.year)

    def test_parse_ad_json_image_extraction(self):
        """Test image URL extraction."""
        # With urls array
        ad1 = {
            "list_id": 123,
            "subject": "Test",
            "attributes": [],
            "images": {
                "urls": ["https://img.example.com/1.jpg", "https://img.example.com/2.jpg"],
            },
        }
        listing1 = self.scraper._parse_ad_json(ad1, "test", "car")
        self.assertEqual(listing1.image_url, "https://img.example.com/1.jpg")

        # With small_url fallback
        ad2 = {
            "list_id": 124,
            "subject": "Test",
            "attributes": [],
            "images": {
                "urls": [],
                "small_url": "https://img.example.com/small.jpg",
            },
        }
        listing2 = self.scraper._parse_ad_json(ad2, "test", "car")
        self.assertEqual(listing2.image_url, "https://img.example.com/small.jpg")

    def test_parse_ad_json_invalid_id(self):
        """Test parsing with missing list_id returns None."""
        ad = {
            "subject": "Test",
            "attributes": [],
        }
        listing = self.scraper._parse_ad_json(ad, "test", "car")
        self.assertIsNone(listing)


class TestScraperSearchParams(unittest.TestCase):
    """Test search parameter building."""

    def setUp(self):
        self.scraper = LeboncoinScraper()

    def test_build_search_params_default(self):
        """Test default search parameters."""
        params = self.scraper._build_search_params(
            brand="mazda",
            model="2",
        )

        self.assertEqual(params["category"], "2")
        self.assertEqual(params["fuel"], "1")  # essence
        self.assertEqual(params["gearbox"], "1")  # manuelle
        self.assertEqual(params["brand"], "mazda")
        self.assertEqual(params["model"], "2")
        self.assertEqual(params["sort"], "time")
        self.assertEqual(params["order"], "desc")

    def test_build_search_params_diesel(self):
        """Test diesel fuel parameter."""
        params = self.scraper._build_search_params(
            brand="peugeot",
            fuel="diesel",
        )
        self.assertEqual(params["fuel"], "2")

    def test_build_search_params_automatic(self):
        """Test automatic gearbox parameter."""
        params = self.scraper._build_search_params(
            brand="honda",
            gearbox="automatique",
        )
        self.assertEqual(params["gearbox"], "2")

    def test_build_search_params_price_range(self):
        """Test price range parameter."""
        params = self.scraper._build_search_params(
            brand="mazda",
            max_price=5000,
        )
        self.assertEqual(params["price"], "0-5000")

    def test_build_search_params_mileage_range(self):
        """Test mileage range parameter."""
        params = self.scraper._build_search_params(
            brand="mazda",
            max_km=100000,
        )
        self.assertEqual(params["mileage"], "0-100000")

    def test_build_search_params_year_range(self):
        """Test year range parameter."""
        params = self.scraper._build_search_params(
            brand="mazda",
            min_year=2010,
        )
        self.assertEqual(params["regdate"], "2010-2025")

    def test_build_search_url(self):
        """Test complete URL building."""
        params = {"brand": "mazda", "model": "2"}
        url = self.scraper._build_search_url(params)

        self.assertIn("leboncoin.fr/recherche", url)
        self.assertIn("brand=mazda", url)
        self.assertIn("model=2", url)
        self.assertIn("category=2", url)


class TestScraperHtmlFallback(unittest.TestCase):
    """Test HTML fallback parsing."""

    def setUp(self):
        self.scraper = LeboncoinScraper()

    def test_parse_html_fallback(self):
        """Test HTML fallback parser finds listings."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_HTML_FALLBACK, "lxml")

        listings = self.scraper._parse_html_fallback(soup, "honda", "jazz")

        self.assertGreater(len(listings), 0)

        # Check first listing
        first = listings[0]
        self.assertEqual(first.listing_id, "9876543210")
        self.assertIn("Honda Jazz", first.title)
        self.assertEqual(first.price, 2500)

    def test_parse_html_fallback_no_ads(self):
        """Test HTML fallback with no ads returns empty list."""
        from bs4 import BeautifulSoup
        html = "<html><body><p>No results</p></body></html>"
        soup = BeautifulSoup(html, "lxml")

        listings = self.scraper._parse_html_fallback(soup, "test", "car")
        self.assertEqual(len(listings), 0)


class TestScraperFullParsing(unittest.TestCase):
    """Test full HTML parsing with embedded JSON."""

    def setUp(self):
        self.scraper = LeboncoinScraper()

    def test_parse_search_results_with_json(self):
        """Test parsing HTML with __NEXT_DATA__ JSON."""
        # Build HTML with embedded JSON
        html = f'''
        <!DOCTYPE html>
        <html>
        <head><title>Search</title></head>
        <body>
            <script id="__NEXT_DATA__" type="application/json">
            {json.dumps(SAMPLE_NEXT_DATA)}
            </script>
        </body>
        </html>
        '''

        listings = self.scraper._parse_search_results(html, "mazda", "2")

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].listing_id, "2345678901")
        self.assertEqual(listings[0].title, "Mazda 2 1.3 MZR 75ch Elegance 5p")

    def test_parse_search_results_falls_back_to_html(self):
        """Test that parser falls back to HTML when no JSON."""
        listings = self.scraper._parse_search_results(
            SAMPLE_HTML_FALLBACK, "honda", "jazz"
        )

        self.assertGreater(len(listings), 0)


class TestScraperConfiguration(unittest.TestCase):
    """Test scraper configuration and initialization."""

    def test_default_configuration(self):
        """Test default scraper configuration."""
        scraper = LeboncoinScraper()

        self.assertEqual(scraper.delay_min, 5.0)
        self.assertEqual(scraper.delay_max, 10.0)
        self.assertEqual(scraper.max_retries, 3)
        self.assertEqual(scraper.timeout, 30.0)

    def test_custom_configuration(self):
        """Test custom scraper configuration."""
        scraper = LeboncoinScraper(
            delay_min=2.0,
            delay_max=5.0,
            max_retries=5,
            timeout=60.0,
        )

        self.assertEqual(scraper.delay_min, 2.0)
        self.assertEqual(scraper.delay_max, 5.0)
        self.assertEqual(scraper.max_retries, 5)
        self.assertEqual(scraper.timeout, 60.0)

    def test_context_manager(self):
        """Test scraper as context manager."""
        with LeboncoinScraper() as scraper:
            self.assertIsNotNone(scraper)

    def test_get_headers(self):
        """Test that headers are realistic."""
        scraper = LeboncoinScraper()
        headers = scraper._get_headers()

        self.assertIn("User-Agent", headers)
        self.assertIn("Mozilla", headers["User-Agent"])
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)


def run_tests():
    """Run all tests with verbose output."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
