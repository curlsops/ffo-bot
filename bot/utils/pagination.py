import discord

from config.constants import Constants

PER_PAGE = 10
DISCORD_LIMIT = Constants.DISCORD_MESSAGE_LIMIT


def truncate_for_discord(content: str) -> str:
    if len(content) <= DISCORD_LIMIT:
        return content
    return content[: DISCORD_LIMIT - 20] + "\n\n...(truncated)"


class ListPaginatedView(discord.ui.View):
    def __init__(
        self,
        rows: list,
        header: str,
        format_row,
        per_page: int | None = None,
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.rows = rows
        self.header = header
        self.format_row = format_row
        self.per_page = per_page if per_page is not None else PER_PAGE
        self.page = 0
        self._max_page = max(0, (len(rows) - 1) // self.per_page)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="list:prev",
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)

        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.success,
            custom_id="list:page",
            disabled=True,
            row=0,
        )
        self.add_item(self.page_btn)

        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="list:next",
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for child in self.children:
            if child.custom_id == "list:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == "list:next":
                child.disabled = self.page >= self._max_page

    def _format_page(self) -> str:
        start = self.page * self.per_page
        chunk = self.rows[start : start + self.per_page]
        lines = [self.format_row(r) for r in chunk]
        return truncate_for_discord(self.header + "\n\n" + "\n".join(lines))

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page <= 0:
            return
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page >= self._max_page:
            return
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(content=self._format_page(), view=self)
