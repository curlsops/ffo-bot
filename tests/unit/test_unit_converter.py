"""TDD tests for unit_converter processor."""

import pytest

from bot.processors.unit_converter import detect_and_convert


class TestDetectAndConvert:
    def test_no_match_returns_none(self):
        assert detect_and_convert("hello world") is None
        assert detect_and_convert("100 kg") is None
        assert detect_and_convert("20 °C") is None

    def test_lb_to_kg(self):
        assert detect_and_convert("I weigh 10 lb") == "I weigh 4.54 kg"
        assert detect_and_convert("5.5 lbs") == "2.49 kg"

    def test_oz_to_kg(self):
        assert detect_and_convert("16 oz") == "454 g"

    def test_ft_to_m(self):
        assert detect_and_convert("5 ft tall") == "1.52 m tall"
        assert detect_and_convert("10 feet") == "3.05 m"

    def test_in_to_cm(self):
        assert detect_and_convert("12 in") == "30.48 cm"
        assert detect_and_convert("6 inches") == "15.24 cm"

    def test_ft_in_combined(self):
        assert detect_and_convert("5'10\"") == "1.78 m"
        assert detect_and_convert("6'2\"") == "1.88 m"

    def test_mi_to_km(self):
        assert detect_and_convert("1 mi") == "1.61 km"
        assert detect_and_convert("26.2 mi marathon") == "42.16 km marathon"

    def test_fahrenheit_to_celsius(self):
        assert detect_and_convert("70°F") == "21.1 °C"
        assert detect_and_convert("32 F") == "0.0 °C"
        assert detect_and_convert("it's 98.6 F outside") == "it's 37.0 °C outside"

    def test_first_match_only(self):
        result = detect_and_convert("10 lb and 5 ft")
        assert result is not None
        assert "4.54 kg" in result
        assert "5 ft" in result

    def test_small_weight_returns_grams(self):
        assert detect_and_convert("1 oz") == "28 g"

    def test_sub_kg_weight(self):
        assert detect_and_convert("0.5 lb") == "227 g"

    def test_small_length_returns_mm(self):
        assert detect_and_convert("0.01 in") == "0.25 mm"

    @pytest.mark.parametrize(
        "text,expected_substr",
        [
            ("2 lb", "907 g"),
            ("3 ft", "91.44 cm"),
            ("212 F", "100"),
            ("1 mi", "1.61 km"),
            ("8 oz", "227 g"),
        ],
    )
    def test_various_conversions(self, text, expected_substr):
        result = detect_and_convert(text)
        assert result is not None
        assert expected_substr in result

    def test_empty_string(self):
        assert detect_and_convert("") is None

    def test_whitespace_only(self):
        assert detect_and_convert("   ") is None

    def test_no_units_in_text(self):
        assert detect_and_convert("just words here") is None

    def test_fahrenheit_conversion(self):
        result = detect_and_convert("it's 68 F today")
        assert result is not None
        assert "°C" in result
