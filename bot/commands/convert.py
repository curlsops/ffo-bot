import logging
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# Units for autocomplete (common + currency)
CONVERT_UNITS = [
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CAD",
    "AUD",
    "m",
    "km",
    "cm",
    "mm",
    "ft",
    "in",
    "mi",
    "kg",
    "g",
    "lb",
    "oz",
    "C",
    "F",
    "celsius",
    "fahrenheit",
]


async def _convert_unit_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current:
        return [app_commands.Choice(name=u, value=u) for u in CONVERT_UNITS[:25]]
    cur = current.upper() if len(current) <= 3 else current.lower()
    matches = [
        app_commands.Choice(name=u, value=u)
        for u in CONVERT_UNITS
        if cur in u.upper() or cur in u.lower()
    ]
    return (
        matches[:25]
        if matches
        else [app_commands.Choice(name=u, value=u) for u in CONVERT_UNITS[:25]]
    )


# Simple measurement conversions (factor to base unit, then to target)
# Base: m, kg, celsius
LENGTH = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "ft": 0.3048, "in": 0.0254, "mi": 1609.34}
WEIGHT = {"kg": 1, "g": 0.001, "lb": 0.453592, "oz": 0.0283495}
TEMP = {"c": 1, "f": 2, "celsius": 1, "fahrenheit": 2}


async def _convert_currency(amount: float, from_cur: str, to_cur: str) -> Optional[float]:
    from_cur = from_cur.upper()[:3]
    to_cur = to_cur.upper()[:3]
    if from_cur == to_cur:
        return amount
    url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_cur}&to={to_cur}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("rates", {}).get(to_cur)
    except Exception as e:
        logger.warning("Currency API error: %s", e)
        return None


def _convert_length(amount: float, from_u: str, to_u: str) -> Optional[float]:
    from_u = from_u.lower()
    to_u = to_u.lower()
    if from_u not in LENGTH or to_u not in LENGTH:
        return None
    meters = amount * LENGTH[from_u]
    return meters / LENGTH[to_u]


def _convert_weight(amount: float, from_u: str, to_u: str) -> Optional[float]:
    from_u = from_u.lower()
    to_u = to_u.lower()
    if from_u not in WEIGHT or to_u not in WEIGHT:
        return None
    kg = amount * WEIGHT[from_u]
    return kg / WEIGHT[to_u]


def _convert_temp(amount: float, from_u: str, to_u: str) -> Optional[float]:
    from_u = from_u.lower()
    to_u = to_u.lower()
    if from_u not in TEMP or to_u not in TEMP:
        return None
    if from_u in ("c", "celsius") and to_u in ("c", "celsius"):
        return amount
    if from_u in ("f", "fahrenheit") and to_u in ("f", "fahrenheit"):
        return amount
    if from_u in ("c", "celsius"):
        return amount * 9 / 5 + 32  # C to F
    return (amount - 32) * 5 / 9  # F to C


class ConvertCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="convert",
        description="Convert currency or measurement (e.g. 100 USD EUR, 5 ft m, 20 C F)",
    )
    @app_commands.describe(
        amount="Amount with unit (e.g. 100, 5.5)",
        from_unit="From unit (USD, EUR, ft, m, kg, lb, C, F)",
        to_unit="To unit",
    )
    @app_commands.autocomplete(
        from_unit=_convert_unit_autocomplete, to_unit=_convert_unit_autocomplete
    )
    async def convert(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_unit: str,
        to_unit: str,
    ):
        await interaction.response.defer(ephemeral=True)

        from_u = from_unit.strip().upper()
        to_u = to_unit.strip().upper()

        # Currency (3-letter codes)
        if len(from_u) == 3 and len(to_u) == 3 and from_u.isalpha() and to_u.isalpha():
            result = await _convert_currency(amount, from_u, to_u)
            if result is not None:
                await interaction.followup.send(
                    f"**{amount:,.2f} {from_u}** ≈ **{result:,.2f} {to_u}**",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                "Currency conversion failed. Check codes (USD, EUR, GBP, etc.).",
                ephemeral=True,
            )
            return

        # Measurement
        from_ul = from_u.lower().replace("°", "")
        to_ul = to_u.lower().replace("°", "")

        result = None
        unit_type = None
        if from_ul in LENGTH and to_ul in LENGTH:
            result = _convert_length(amount, from_ul, to_ul)
            unit_type = "length"
        elif from_ul in WEIGHT and to_ul in WEIGHT:
            result = _convert_weight(amount, from_ul, to_ul)
            unit_type = "weight"
        elif from_ul in TEMP and to_ul in TEMP:
            result = _convert_temp(amount, from_ul, to_ul)
            unit_type = "temp"

        if result is not None:
            fmt = f"{result:,.2f}" if unit_type != "temp" else f"{result:.1f}"
            await interaction.followup.send(
                f"**{amount:,.2f} {from_u}** = **{fmt} {to_u}**",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "Unsupported units. Use: USD/EUR/GBP (currency), m/ft/cm/in (length), kg/lb (weight), C/F (temp).",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(ConvertCommands(bot))
