import pytest

from bot.processors.unit_converter import convert_in_text, detect_and_convert


class TestDetectAndConvert:
    @pytest.mark.parametrize(
        "text",
        [
            "hello world",
            "100 kg",
            "20 °C",
            "no units",
            "100",
            "kg",
            "meters",
            "°C",
            "",
            "   ",
            "just words here",
        ],
    )
    def test_no_match_returns_none(self, text):
        assert detect_and_convert(text) is None

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("I weigh 10 lb", "I weigh 4.54 kg"),
            ("5.5 lbs", "2.49 kg"),
            ("10 lb", "4.54 kg"),
            ("1 lb", "454 g"),
            ("100 lb", "45.36 kg"),
            ("0.5 lb", "227 g"),
            ("2 pounds", "907 g"),
            ("16 oz", "454 g"),
            ("1 oz", "28 g"),
            ("8 oz", "227 g"),
            ("5 ft tall", "1.52 m tall"),
            ("10 feet", "3.05 m"),
            ("1 ft", "30.48 cm"),
            ("100 ft", "30.48 m"),
            ("12 in", "30.48 cm"),
            ("6 inches", "15.24 cm"),
            ("1 in", "2.54 cm"),
            ("0.01 in", "0.25 mm"),
            ("1 mi", "1.61 km"),
            ("26.2 mi marathon", "42.16 km marathon"),
            ("0.1 mi", "160.93 m"),
            ("70°F", "21.1 °C"),
            ("32 F", "0.0 °C"),
            ("it's 98.6 F outside", "it's 37.0 °C outside"),
        ],
    )
    def test_exact_conversions(self, text, expected):
        assert detect_and_convert(text) == expected

    @pytest.mark.parametrize(
        "text,expected_substr",
        [
            ("2 lb", "907 g"),
            ("3 ft", "91.44 cm"),
            ("212 F", "100"),
            ("1 mi", "1.61 km"),
            ("8 oz", "227 g"),
            ("0 F", "-17.8"),
            ("68 F", "°C"),
        ],
    )
    def test_various_conversions(self, text, expected_substr):
        result = detect_and_convert(text)
        assert result is not None
        assert expected_substr in result

    def test_first_match_only(self):
        result = detect_and_convert("10 lb and 5 ft")
        assert result is not None
        assert "4.54 kg" in result
        assert "5 ft" in result

    @pytest.mark.parametrize("height", ["5'10\"", "6'0\"", "5'9\"", "6'2\""])
    def test_ft_in_combined(self, height):
        result = detect_and_convert(height)
        assert result is not None
        assert "m" in result

    def test_convert_in_text_no_match(self):
        assert convert_in_text("hello") is None

    def test_convert_in_text_match(self):
        result = convert_in_text("I weigh 10 lb")
        assert result is not None
        assert "4.54 kg" in result
