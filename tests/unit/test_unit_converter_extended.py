import pytest

from bot.processors.unit_converter import convert_in_text, detect_and_convert


class TestUnitConverterExtended:
    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("10 lb", "4.54 kg"),
            ("1 lb", "454 g"),
            ("100 lb", "45.36 kg"),
            ("0.5 lb", "227 g"),
            ("2 pounds", "907 g"),
        ],
    )
    def test_weight_conversions(self, text, expected_contains):
        result = detect_and_convert(text)
        assert result is not None
        assert expected_contains in result

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("1 ft", "30.48 cm"),
            ("100 ft", "30.48 m"),
            ("1 in", "2.54 cm"),
            ("12 inches", "30.48 cm"),
            ("1 mi", "1.61 km"),
            ("0.1 mi", "160.93 m"),
        ],
    )
    def test_length_conversions(self, text, expected_contains):
        result = detect_and_convert(text)
        assert result is not None
        assert expected_contains in result

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("32 F", "0.0"),
            ("212 F", "100"),
            ("98.6 F", "37.0"),
            ("0 F", "-17.8"),
            ("70°F", "21.1"),
        ],
    )
    def test_temp_conversions(self, text, expected_contains):
        result = detect_and_convert(text)
        assert result is not None
        assert expected_contains in result
        assert "°C" in result

    @pytest.mark.parametrize("text", ["no units", "100", "kg", "meters", "°C"])
    def test_no_conversion_returns_none(self, text):
        assert detect_and_convert(text) is None

    def test_convert_in_text_no_match(self):
        assert convert_in_text("hello") is None

    def test_convert_in_text_match(self):
        assert "4.54 kg" in convert_in_text("I weigh 10 lb")

    @pytest.mark.parametrize("height", ["5'10\"", "6'0\"", "5'9\"", "6'2\""])
    def test_ft_in_heights(self, height):
        result = detect_and_convert(height)
        assert result is not None
        assert "m" in result
