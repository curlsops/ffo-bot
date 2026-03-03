from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.commands.convert import (
    ConvertCommands,
    _convert_length,
    _convert_temp,
    _convert_weight,
)


@pytest.fixture
def cog():
    return ConvertCommands(MagicMock())


def _interaction():
    i = MagicMock(guild_id=1, channel_id=2)
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


class TestConvertLengthUnits:
    @pytest.mark.parametrize("unit", ["m", "km", "cm", "mm", "ft", "in", "mi"])
    def test_unit_recognized(self, unit):
        assert _convert_length(1, unit, unit) == 1


class TestConvertLength:
    def test_ft_to_m(self):
        assert abs(_convert_length(1, "ft", "m") - 0.3048) < 0.001

    def test_in_to_cm(self):
        assert abs(_convert_length(1, "in", "cm") - 2.54) < 0.01

    def test_unknown_unit_returns_none(self):
        assert _convert_length(1, "xyz", "m") is None

    @pytest.mark.parametrize(
        "amount,from_u,to_u,expected",
        [
            (1, "m", "km", 0.001),
            (1000, "m", "km", 1),
            (1, "km", "m", 1000),
            (1, "cm", "m", 0.01),
            (1, "ft", "in", 12),
            (1, "mi", "ft", 5280),
        ],
    )
    def test_length_conversions(self, amount, from_u, to_u, expected):
        result = _convert_length(amount, from_u, to_u)
        assert result is not None
        assert abs(result - expected) < max(0.02, expected * 0.001)


class TestConvertWeight:
    def test_lb_to_kg(self):
        assert abs(_convert_weight(1, "lb", "kg") - 0.453592) < 0.001

    def test_oz_to_g(self):
        result = _convert_weight(1, "oz", "g")
        assert result is not None
        assert result > 20

    @pytest.mark.parametrize(
        "amount,from_u,to_u",
        [
            (1, "kg", "g"),
            (1000, "g", "kg"),
            (2, "lb", "kg"),
            (1, "oz", "lb"),
        ],
    )
    def test_weight_conversions(self, amount, from_u, to_u):
        result = _convert_weight(amount, from_u, to_u)
        assert result is not None
        assert result > 0


class TestConvertTemp:
    def test_f_to_c_freezing(self):
        assert abs(_convert_temp(32, "f", "c") - 0) < 0.01

    def test_f_to_c_boiling(self):
        assert abs(_convert_temp(212, "f", "c") - 100) < 0.01

    def test_c_to_c_no_change(self):
        assert _convert_temp(20, "c", "celsius") == 20

    @pytest.mark.parametrize(
        "amount,from_u,to_u,expected",
        [
            (0, "c", "f", 32),
            (100, "c", "f", 212),
            (-40, "c", "f", -40),
            (212, "f", "c", 100),
        ],
    )
    def test_temp_conversions(self, amount, from_u, to_u, expected):
        result = _convert_temp(amount, from_u, to_u)
        assert result is not None
        assert abs(result - expected) < 0.1


class TestConvertCommand:
    @pytest.mark.asyncio
    async def test_convert_currency(self, cog):
        with patch(
            "bot.commands.convert._convert_currency", new_callable=AsyncMock, return_value=0.92
        ):
            i = _interaction()
            await cog.convert.callback(cog, i, 100, "USD", "EUR")
            call = i.followup.send.call_args
            assert "92" in call[0][0]
            assert "EUR" in call[0][0]

    @pytest.mark.asyncio
    async def test_convert_length(self, cog):
        i = _interaction()
        await cog.convert.callback(cog, i, 5, "ft", "m")
        call = i.followup.send.call_args
        assert "1.52" in call[0][0] or "1.53" in call[0][0]

    @pytest.mark.asyncio
    async def test_convert_unsupported_units(self, cog):
        i = _interaction()
        await cog.convert.callback(cog, i, 10, "xx", "yy")  # not in any unit dict
        call = i.followup.send.call_args
        assert "Unsupported" in call[0][0]
        assert call[1].get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_convert_weight(self, cog):
        i = _interaction()
        await cog.convert.callback(cog, i, 1, "kg", "lb")
        call = i.followup.send.call_args
        assert "lb" in call[0][0].lower() or "2.2" in call[0][0]

    @pytest.mark.asyncio
    async def test_convert_temp(self, cog):
        i = _interaction()
        await cog.convert.callback(cog, i, 0, "c", "f")
        call = i.followup.send.call_args
        assert "32" in call[0][0]

    @pytest.mark.asyncio
    async def test_convert_zero_amount(self, cog):
        i = _interaction()
        await cog.convert.callback(cog, i, 0, "m", "km")
        call = i.followup.send.call_args
        assert "0" in call[0][0]
