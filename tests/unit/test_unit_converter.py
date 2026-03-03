"""TDD tests for unit_converter processor."""

import pytest

from bot.processors.unit_converter import detect_and_convert


class TestDetectAndConvert:
    def test_no_match_returns_none(self):
        assert detect_and_convert("hello world") is None
        assert detect_and_convert("100 kg") is None  # already SI
        assert detect_and_convert("20 °C") is None  # already SI

    def test_lb_to_kg(self):
        assert detect_and_convert("I weigh 10 lb") == "4.54 kg"
        assert detect_and_convert("5.5 lbs") == "2.49 kg"

    def test_oz_to_kg(self):
        assert detect_and_convert("16 oz") == "454 g"

    def test_ft_to_m(self):
        assert detect_and_convert("5 ft tall") == "1.52 m"
        assert detect_and_convert("10 feet") == "3.05 m"

    def test_in_to_cm(self):
        assert detect_and_convert("12 in") == "30.48 cm"
        assert detect_and_convert("6 inches") == "15.24 cm"

    def test_ft_in_combined(self):
        assert detect_and_convert("5'10\"") == "1.78 m"
        assert detect_and_convert("6'2\"") == "1.88 m"

    def test_mi_to_km(self):
        assert detect_and_convert("1 mi") == "1.61 km"
        assert detect_and_convert("26.2 mi marathon") == "42.16 km"

    def test_fahrenheit_to_celsius(self):
        assert detect_and_convert("70°F") == "21.1 °C"
        assert detect_and_convert("32 F") == "0.0 °C"
        assert detect_and_convert("it's 98.6 F outside") == "37.0 °C"

    def test_first_match_only(self):
        # Should return first match, not multiple
        result = detect_and_convert("10 lb and 5 ft")
        assert result is not None
        assert "kg" in result or "m" in result

    def test_small_weight_returns_grams(self):
        """Covers _to_si_weight when kg < 1 (returns g)."""
        assert detect_and_convert("1 oz") == "28 g"

    def test_sub_kg_weight(self):
        """Covers weight_imperial branch returning g."""
        assert detect_and_convert("0.5 lb") == "227 g"

    def test_small_length_returns_mm(self):
        """Covers _to_si_length when meters < 0.01 (returns mm)."""
        assert detect_and_convert("0.01 in") == "0.25 mm"
