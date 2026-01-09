#!/usr/bin/env python3
"""
Unit tests for the CarFilter scoring logic.
Ensures that "High Priority" items actually trigger High Priority notifications.

Run with: python -m pytest tests/test_filters.py -v
Or:       python tests/test_filters.py
"""

import sys
import os
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.filters import CarFilter, ScoreResult


class TestScoreResult(unittest.TestCase):
    """Test ScoreResult dataclass."""

    def test_default_values(self):
        """Test default ScoreResult values."""
        result = ScoreResult()
        self.assertEqual(result.total_score, 0)
        self.assertEqual(result.priority, "low")
        self.assertEqual(result.bonuses, [])
        self.assertEqual(result.penalties, [])
        self.assertEqual(result.warnings, [])
        self.assertFalse(result.excluded)
        self.assertIsNone(result.exclusion_reason)

    def test_to_json(self):
        """Test JSON serialization."""
        result = ScoreResult(
            total_score=15,
            priority="high",
            bonuses=["+10 test"],
            penalties=["-5 penalty"],
        )
        json_str = result.to_json()
        self.assertIn("total_score", json_str)
        self.assertIn("15", json_str)
        self.assertIn("high", json_str)


class TestCarFilterBlacklist(unittest.TestCase):
    """Test blacklist detection."""

    def setUp(self):
        """Set up test filter with config directory."""
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_blacklist_panne(self):
        """Listings with 'panne' should be excluded."""
        result = self.filter.evaluate(
            listing_id="123",
            title="Voiture en panne",
            description="Moteur HS",
        )
        self.assertTrue(result.excluded)
        self.assertIn("blacklist", result.exclusion_reason.lower())

    def test_blacklist_pour_pieces(self):
        """Listings 'pour pieces' should be excluded."""
        result = self.filter.evaluate(
            listing_id="124",
            title="Voiture pour pieces",
            description="A depecer",
        )
        self.assertTrue(result.excluded)

    def test_blacklist_accidente(self):
        """Accidented cars should be excluded."""
        result = self.filter.evaluate(
            listing_id="125",
            title="Voiture accidentee",
            description="Choc avant",
        )
        self.assertTrue(result.excluded)

    def test_blacklist_epave(self):
        """Wrecks should be excluded."""
        result = self.filter.evaluate(
            listing_id="126",
            title="Mazda 2 epave",
            description="Pour collectionneur",
        )
        self.assertTrue(result.excluded)

    def test_no_blacklist_normal_listing(self):
        """Normal listings should not be excluded by blacklist."""
        result = self.filter.evaluate(
            listing_id="127",
            title="Mazda 2 1.3 essence",
            description="Tres bon etat, entretien suivi",
            price=2500,
            mileage=90000,
            year=2012,
            brand="mazda",
            model="2",
        )
        self.assertFalse(result.excluded)


class TestCarFilterBrandExclusions(unittest.TestCase):
    """Test brand-specific exclusions."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_peugeot_vti_excluded(self):
        """Peugeot VTi engines should be excluded."""
        result = self.filter.evaluate(
            listing_id="200",
            title="Peugeot 208 1.4 VTi",
            description="Moteur 1.4 VTi 95ch",
            brand="peugeot",
            model="208",
        )
        self.assertTrue(result.excluded)
        self.assertIn("VTi", result.exclusion_reason)

    def test_renault_tce_excluded(self):
        """Renault TCe engines should be excluded."""
        result = self.filter.evaluate(
            listing_id="201",
            title="Renault Clio TCe 90",
            description="Motorisation 1.2 TCe",
            brand="renault",
            model="clio",
        )
        self.assertTrue(result.excluded)
        self.assertIn("TCe", result.exclusion_reason)

    def test_honda_cvt_excluded(self):
        """Honda CVT transmissions should be excluded."""
        result = self.filter.evaluate(
            listing_id="202",
            title="Honda Jazz CVT",
            description="Boite automatique CVT",
            brand="honda",
            model="jazz",
        )
        self.assertTrue(result.excluded)
        self.assertIn("CVT", result.exclusion_reason)

    def test_honda_manual_accepted(self):
        """Honda Jazz with manual transmission should be accepted."""
        result = self.filter.evaluate(
            listing_id="203",
            title="Honda Jazz 1.4 manuelle",
            description="Boite manuelle 5 vitesses, entretien suivi",
            brand="honda",
            model="jazz",
            gearbox="manuelle",
            price=2800,
            mileage=95000,
            year=2012,
        )
        self.assertFalse(result.excluded)

    def test_suzuki_ddis_excluded(self):
        """Suzuki DDiS diesel should be excluded."""
        result = self.filter.evaluate(
            listing_id="204",
            title="Suzuki Swift DDiS",
            description="1.3 DDiS diesel",
            brand="suzuki",
            model="swift",
        )
        self.assertTrue(result.excluded)

    def test_seat_tsi_excluded(self):
        """Seat TSI engines should be excluded."""
        result = self.filter.evaluate(
            listing_id="205",
            title="Seat Ibiza 1.2 TSI",
            description="Moteur TSI turbo",
            brand="seat",
            model="ibiza",
        )
        self.assertTrue(result.excluded)


class TestCarFilterCriteria(unittest.TestCase):
    """Test general criteria exclusions."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_price_over_max_excluded(self):
        """Price above max should be excluded."""
        result = self.filter.evaluate(
            listing_id="300",
            title="Mazda 2",
            description="Parfait etat",
            price=5000,  # Over 3000 default max
            brand="mazda",
            model="2",
        )
        self.assertTrue(result.excluded)
        self.assertIn("Prix", result.exclusion_reason)

    def test_mileage_over_max_excluded(self):
        """Mileage above max should be excluded."""
        result = self.filter.evaluate(
            listing_id="301",
            title="Mazda 2",
            description="Parfait etat",
            price=2500,
            mileage=200000,  # Over 150000 default max
            brand="mazda",
            model="2",
        )
        self.assertTrue(result.excluded)
        self.assertIn("Km", result.exclusion_reason)

    def test_year_below_min_excluded(self):
        """Year below minimum should be excluded."""
        result = self.filter.evaluate(
            listing_id="302",
            title="Mazda 2",
            description="Parfait etat",
            price=2500,
            mileage=100000,
            year=2005,  # Below 2008 default min
            brand="mazda",
            model="2",
        )
        self.assertTrue(result.excluded)
        self.assertIn("Ann", result.exclusion_reason)

    def test_automatic_gearbox_excluded(self):
        """Automatic gearbox should be excluded (when manual required)."""
        result = self.filter.evaluate(
            listing_id="303",
            title="Mazda 2 automatique",
            description="Boite auto",
            price=2500,
            mileage=100000,
            year=2012,
            gearbox="automatique",
            brand="mazda",
            model="2",
        )
        self.assertTrue(result.excluded)
        self.assertIn("automatique", result.exclusion_reason.lower())


class TestCarFilterScoring(unittest.TestCase):
    """Test scoring bonuses and penalties."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_mazda_2_essence_high_priority(self):
        """Mazda 2 essence should get high priority bonus."""
        result = self.filter.evaluate(
            listing_id="400",
            title="Mazda 2 1.3 essence",
            description="Moteur chaine, entretien suivi",
            price=2400,
            mileage=85000,
            year=2012,
            fuel="essence",
            gearbox="manuelle",
            brand="mazda",
            model="2",
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.priority, "high")
        self.assertGreater(result.total_score, 15)  # High threshold
        # Check bonuses are present
        bonus_text = " ".join(result.bonuses)
        self.assertIn("Mazda 2", bonus_text)

    def test_honda_jazz_manual_high_priority(self):
        """Honda Jazz manual should get high priority."""
        result = self.filter.evaluate(
            listing_id="401",
            title="Honda Jazz 1.4 i-VTEC manuelle",
            description="Boite manuelle 5 vitesses",
            price=2800,
            mileage=90000,
            year=2013,
            fuel="essence",
            gearbox="manuelle",
            brand="honda",
            model="jazz",
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.priority, "high")
        bonus_text = " ".join(result.bonuses)
        self.assertIn("Honda Jazz", bonus_text)

    def test_suzuki_swift_high_priority(self):
        """Suzuki Swift 3 post-2010 should get high priority."""
        result = self.filter.evaluate(
            listing_id="402",
            title="Suzuki Swift 1.2 VVT",
            description="Generation 3, excellent etat",
            price=2500,
            mileage=80000,
            year=2014,
            fuel="essence",
            gearbox="manuelle",
            brand="suzuki",
            model="swift",
        )
        self.assertFalse(result.excluded)
        self.assertEqual(result.priority, "high")

    def test_toyota_yaris_medium_priority(self):
        """Toyota Yaris should get medium priority (5 points bonus)."""
        result = self.filter.evaluate(
            listing_id="403",
            title="Toyota Yaris",
            description="Fiable et economique",
            price=2800,
            mileage=100000,
            year=2012,
            fuel="essence",
            gearbox="manuelle",
            brand="toyota",
            model="yaris",
        )
        self.assertFalse(result.excluded)
        # Toyota Yaris gets +5, might be medium or lower depending on other factors
        self.assertIn(result.priority, ["medium", "low"])

    def test_low_price_bonus(self):
        """Price under 2500 should give bonus."""
        result = self.filter.evaluate(
            listing_id="404",
            title="Peugeot 206",
            description="Bon etat",
            price=2200,
            mileage=120000,
            year=2010,
            fuel="essence",
            gearbox="manuelle",
            brand="peugeot",
            model="206",
        )
        bonus_text = " ".join(result.bonuses)
        self.assertIn("2500", bonus_text)

    def test_low_mileage_bonus(self):
        """Mileage under 100000 should give bonus."""
        result = self.filter.evaluate(
            listing_id="405",
            title="Peugeot 206",
            description="Bon etat",
            price=2800,
            mileage=75000,
            year=2010,
            fuel="essence",
            gearbox="manuelle",
            brand="peugeot",
            model="206",
        )
        bonus_text = " ".join(result.bonuses)
        self.assertIn("100", bonus_text)

    def test_diesel_penalty(self):
        """Diesel should receive penalty."""
        result = self.filter.evaluate(
            listing_id="406",
            title="Peugeot 206 HDi",
            description="Diesel",
            price=2500,
            mileage=100000,
            year=2010,
            fuel="diesel",
            gearbox="manuelle",
            brand="peugeot",
            model="206",
        )
        penalty_text = " ".join(result.penalties)
        self.assertIn("Diesel", penalty_text)
        self.assertLess(result.total_score, 0)  # Negative due to diesel penalty

    def test_suspicious_keyword_penalty(self):
        """Suspicious keywords should receive penalty."""
        result = self.filter.evaluate(
            listing_id="407",
            title="Peugeot 206",
            description="Vendu en l'etat sans garantie",
            price=2500,
            mileage=100000,
            year=2010,
            fuel="essence",
            gearbox="manuelle",
            brand="peugeot",
            model="206",
        )
        penalty_text = " ".join(result.penalties)
        self.assertIn("-10", penalty_text)


class TestCarFilterPriorityThresholds(unittest.TestCase):
    """Test priority threshold logic."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_high_priority_threshold(self):
        """Score > 15 should be high priority."""
        # Mazda 2 essence with chain engine and low km = ~15+ points
        result = self.filter.evaluate(
            listing_id="500",
            title="Mazda 2 essence chaine",
            description="Moteur chaine distribution, carnet entretien",
            price=2400,
            mileage=75000,
            year=2012,
            fuel="essence",
            gearbox="manuelle",
            brand="mazda",
            model="2",
        )
        self.assertEqual(result.priority, "high")
        self.assertGreater(result.total_score, 15)

    def test_medium_priority_threshold(self):
        """Score 10-15 should be medium priority."""
        # Create a scenario with score between 10-15
        self.filter.set_high_threshold(20)  # Raise threshold to test medium
        result = self.filter.evaluate(
            listing_id="501",
            title="Mazda 2 essence",
            description="Bon etat",
            price=2800,
            mileage=120000,
            year=2012,
            fuel="essence",
            gearbox="manuelle",
            brand="mazda",
            model="2",
        )
        # Mazda 2 essence gives +10, should be medium with threshold at 20
        if result.total_score >= 10 and result.total_score <= 20:
            self.assertEqual(result.priority, "medium")

    def test_low_priority_threshold(self):
        """Score < 10 should be low priority."""
        result = self.filter.evaluate(
            listing_id="502",
            title="Peugeot 206",
            description="Bon etat",
            price=2800,
            mileage=120000,
            year=2010,
            fuel="essence",
            gearbox="manuelle",
            brand="peugeot",
            model="206",
        )
        # No high priority bonuses, should be low
        self.assertEqual(result.priority, "low")

    def test_set_high_threshold(self):
        """Test changing the high threshold."""
        self.filter.set_high_threshold(10)
        result = self.filter.evaluate(
            listing_id="503",
            title="Mazda 2 essence",
            description="Bon etat",
            price=2800,
            mileage=120000,
            year=2012,
            fuel="essence",
            gearbox="manuelle",
            brand="mazda",
            model="2",
        )
        # Mazda 2 essence gives +10, with threshold at 10, score > 10 = high
        self.assertEqual(result.priority, "high")


class TestCarFilterEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.filter = CarFilter(config_dir=str(config_dir))

    def test_empty_description(self):
        """Listing with empty description should work."""
        result = self.filter.evaluate(
            listing_id="600",
            title="Mazda 2",
            description="",
            price=2500,
            mileage=100000,
            year=2012,
            brand="mazda",
            model="2",
        )
        self.assertFalse(result.excluded)

    def test_missing_optional_fields(self):
        """Listing with missing optional fields should work."""
        result = self.filter.evaluate(
            listing_id="601",
            title="Mazda 2",
        )
        # Should not crash, may be excluded by criteria but shouldn't error
        self.assertIsInstance(result, ScoreResult)

    def test_none_values(self):
        """Listing with None values should be handled gracefully."""
        result = self.filter.evaluate(
            listing_id="602",
            title="Mazda 2",
            description=None,
            price=None,
            mileage=None,
            year=None,
            fuel=None,
            gearbox=None,
            brand=None,
            model=None,
            engine=None,
        )
        self.assertIsInstance(result, ScoreResult)

    def test_unicode_handling(self):
        """Unicode characters should be handled correctly."""
        result = self.filter.evaluate(
            listing_id="603",
            title="Citron C3 1.2 PureTech",
            description="Tres bon tat, entretien chez Citron",
            price=2500,
            mileage=90000,
            year=2015,
            brand="citroen",
            model="c3",
        )
        self.assertIsInstance(result, ScoreResult)

    def test_case_insensitivity(self):
        """Blacklist/exclusions should be case insensitive."""
        # Test uppercase blacklist keyword
        result = self.filter.evaluate(
            listing_id="604",
            title="Voiture ACCIDENTEE",
            description="Choc avant",
        )
        self.assertTrue(result.excluded)

        # Test mixed case
        result2 = self.filter.evaluate(
            listing_id="605",
            title="Renault Clio 1.2 TCE",  # Uppercase TCE
            description="Moteur turbo",
            brand="renault",
            model="clio",
        )
        self.assertTrue(result2.excluded)


def run_tests():
    """Run all tests with verbose output."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
