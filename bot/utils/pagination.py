import discord

from config.constants import Constants

PER_PAGE = 10
DISCORD_LIMIT = Constants.DISCORD_MESSAGE_LIMIT


def paginate_by_char_limit(blocks: list[str], limit: int) -> list[str]:
    pages = []
    current = []
    current_len = 0
    for block in blocks:
        block_len = len(block)
        if current_len + block_len > limit and current:
            pages.append("".join(current))
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len
    if current:
        pages.append("".join(current))
    return pages


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
        extra_items: list[discord.ui.Item] | None = None,
        custom_id_prefix: str = "list",
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.rows = rows
        self.header = header
        self.format_row = format_row
        self.per_page = per_page if per_page is not None else PER_PAGE
        self.page = 0
        self._max_page = max(0, (len(rows) - 1) // self.per_page)
        p = custom_id_prefix

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{p}:prev",
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)

        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.success,
            custom_id=f"{p}:page",
            disabled=True,
            row=0,
        )
        self.add_item(self.page_btn)

        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{p}:next",
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)
        if extra_items:
            for item in extra_items:
                self.add_item(item)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        p = self.page_btn.custom_id.split(":")[0]
        for child in self.children:
            if child.custom_id == f"{p}:prev":
                child.disabled = self.page <= 0
            elif child.custom_id == f"{p}:next":
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


class EmbedListPaginatedView(discord.ui.View):
    def __init__(
        self,
        rows: list,
        format_row,
        title: str = "",
        per_page: int | None = None,
        empty_msg: str = "—",
        color: int | discord.Color | None = None,
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.rows = rows
        self.format_row = format_row
        self.title = title
        self.per_page = per_page if per_page is not None else PER_PAGE
        self.empty_msg = empty_msg
        self.color = color if color is not None else discord.Color.blue()
        self.page = 0
        self._max_page = max(0, (len(rows) - 1) // self.per_page)

        prev_b = discord.ui.Button(
            label="◀", style=discord.ButtonStyle.secondary, custom_id="el:prev", row=0
        )
        prev_b.callback = self._prev_callback
        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.primary,
            custom_id="el:page",
            disabled=True,
            row=0,
        )
        next_b = discord.ui.Button(
            label="▶", style=discord.ButtonStyle.secondary, custom_id="el:next", row=0
        )
        next_b.callback = self._next_callback
        for b in (prev_b, self.page_btn, next_b):
            self.add_item(b)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for c in self.children:
            if c.custom_id == "el:prev":
                c.disabled = self.page <= 0
            elif c.custom_id == "el:next":
                c.disabled = self.page >= self._max_page

    def _format_page(self) -> discord.Embed:
        start = self.page * self.per_page
        chunk = self.rows[start : start + self.per_page]
        lines = [self.format_row(r) for r in chunk]
        desc = truncate_for_discord("\n".join(lines)) if lines else self.empty_msg
        return discord.Embed(title=self.title, description=desc[:4096], color=self.color)

    async def _prev_callback(self, i: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            await i.response.edit_message(embed=self._format_page(), view=self)

    async def _next_callback(self, i: discord.Interaction):
        if self.page < self._max_page:
            self.page += 1
            self._update_buttons()
            await i.response.edit_message(embed=self._format_page(), view=self)


class EmbedPaginatedView(discord.ui.View):
    def __init__(
        self,
        pages: list[str],
        title: str = "",
        footer: str = "",
        footer_template: str = "",
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.footer = footer
        self.footer_template = footer_template
        self.page = 0
        self._max_page = max(0, len(pages) - 1)
        prev_b = discord.ui.Button(
            label="◀", style=discord.ButtonStyle.secondary, custom_id="ep:prev", row=0
        )
        prev_b.callback = self._prev_callback
        self.page_btn = discord.ui.Button(
            label="1/1",
            style=discord.ButtonStyle.primary,
            custom_id="ep:page",
            disabled=True,
            row=0,
        )
        next_b = discord.ui.Button(
            label="▶", style=discord.ButtonStyle.secondary, custom_id="ep:next", row=0
        )
        next_b.callback = self._next_callback
        for b in (prev_b, self.page_btn, next_b):
            self.add_item(b)
        self._update_buttons()

    def _update_buttons(self):
        self.page_btn.label = f"{self.page + 1}/{self._max_page + 1}"
        for c in self.children:
            if c.custom_id == "ep:prev":
                c.disabled = self.page <= 0
            elif c.custom_id == "ep:next":
                c.disabled = self.page >= self._max_page

    def _format_page(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.title, description=self.pages[self.page][:4096], color=discord.Color.blue()
        )
        if self.footer_template:
            embed.set_footer(
                text=self.footer_template.format(page=self.page + 1, total=self._max_page + 1)
            )
        elif self.footer:
            embed.set_footer(text=self.footer)
        return embed

    async def _prev_callback(self, i: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            await i.response.edit_message(embed=self._format_page(), view=self)

    async def _next_callback(self, i: discord.Interaction):
        if self.page < self._max_page:
            self.page += 1
            self._update_buttons()
            await i.response.edit_message(embed=self._format_page(), view=self)
