"""TDD tests for convert command."""

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


class TestConvertLength:
    def test_ft_to_m(self):
        assert abs(_convert_length(1, "ft", "m") - 0.3048) < 0.001

    def test_in_to_cm(self):
        assert abs(_convert_length(1, "in", "cm") - 2.54) < 0.01

    def test_unknown_unit_returns_none(self):
        assert _convert_length(1, "xyz", "m") is None


class TestConvertWeight:
    def test_lb_to_kg(self):
        assert abs(_convert_weight(1, "lb", "kg") - 0.453592) < 0.001

    def test_oz_to_g(self):
        result = _convert_weight(1, "oz", "g")
        assert result is not None
        assert result > 20


class TestConvertTemp:
    def test_f_to_c_freezing(self):
        assert abs(_convert_temp(32, "f", "c") - 0) < 0.01

    def test_f_to_c_boiling(self):
        assert abs(_convert_temp(212, "f", "c") - 100) < 0.01

    def test_c_to_c_no_change(self):
        assert _convert_temp(20, "c", "celsius") == 20


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
