"""Discord-бот: /ladder (кнопки выбора класса/спека, пагинация, тренды) + /roster."""
from __future__ import annotations

import logging
import math
from typing import List, Optional

import discord
from discord import app_commands

import roster
from config import CONFIG
from ladder import LadderCache, LadderResult, LadderRow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

CLASSES = [
    "Death Knight", "Druid", "Hunter", "Mage", "Paladin",
    "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
]

CLASS_EMOJI = {
    "Death Knight": "💀", "Druid": "🌿", "Hunter": "🏹", "Mage": "❄️",
    "Paladin": "🔨", "Priest": "🙏", "Rogue": "🗡️", "Shaman": "⚡",
    "Warlock": "🔥", "Warrior": "⚔️",
}

# Названия спеков по порядку талант-деревьев 3.3.5 (spec 1/2/3 на UwU).
SPEC_NAMES = {
    "Warrior": {1: "Arms", 2: "Fury", 3: "Protection"},
    "Paladin": {1: "Holy", 2: "Protection", 3: "Retribution"},
    "Hunter": {1: "Beast Mastery", 2: "Marksmanship", 3: "Survival"},
    "Rogue": {1: "Assassination", 2: "Combat", 3: "Subtlety"},
    "Priest": {1: "Discipline", 2: "Holy", 3: "Shadow"},
    "Death Knight": {1: "Blood", 2: "Frost", 3: "Unholy"},
    "Shaman": {1: "Elemental", 2: "Enhancement", 3: "Restoration"},
    "Mage": {1: "Arcane", 2: "Fire", 3: "Frost"},
    "Warlock": {1: "Affliction", 2: "Demonology", 3: "Destruction"},
    "Druid": {1: "Balance", 2: "Feral", 3: "Restoration"},
}

PAGE_SIZE = 25
COLOR = 0x9B59B6
ALL_OPT = "__all__"  # непустое значение-заглушка: Discord требует value длиной 1–100


def _spec_label(class_name, spec) -> str:
    if not spec:
        return ""
    return SPEC_NAMES.get(class_name, {}).get(spec, f"спек {spec}")


def _fmt_rating(rating) -> str:
    return "-" if rating is None else f"{rating:.2f}"


def _crown(name: str) -> str:
    # Корона для «своих»: любой ник, где встречается Egor (напр. Egormashina).
    return " 👑" if "egor" in (name or "").lower() else ""


def _trend(row: LadderRow) -> str:
    if row.prev_rank is None:
        return "🆕"
    d = row.prev_rank - row.rank
    if d > 0:
        return f"🔺{d}"
    if d < 0:
        return f"🔻{-d}"
    return "➖"


def _filter_rows(result: LadderResult, class_name, spec, limit) -> List[LadderRow]:
    rows = result.rows
    if limit and limit > 0:
        rows = rows[:limit]
    if class_name:
        cl = class_name.lower()
        rows = [r for r in rows if (r.member.class_name or "").lower() == cl]
    if spec:
        rows = [r for r in rows if r.rating.spec == spec and r.rating.rating is not None]
    elif class_name:
        # для класс-фильтра прячем тех, у кого нет данных
        rows = [r for r in rows if r.rating.rating is not None]
    return rows


def _title(class_name, spec) -> str:
    if class_name and spec:
        return f"🏆 Топ {_spec_label(class_name, spec)} {class_name}"
    if class_name:
        return f"🏆 Топ {class_name}"
    return f"🏆 Ладдер {CONFIG.warmane_guild} @ {CONFIG.warmane_realm}"


def render_embed(result: LadderResult, class_name, spec, page, limit) -> discord.Embed:
    rows = _filter_rows(result, class_name, spec, limit)
    show_trend = not class_name and not spec
    total = len(rows)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    start = page * PAGE_SIZE
    chunk = rows[start:start + PAGE_SIZE]

    lines: List[str] = []
    for idx, row in enumerate(chunk):
        pos = start + idx + 1
        m = row.member
        emoji = CLASS_EMOJI.get(m.class_name, "▫️")
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"`#{pos:<3}`")
        crown = _crown(m.name)
        if row.rating.profile_url:
            name_link = f"[{m.name}]({row.rating.profile_url})"
        else:
            name_link = m.name
        rating = _fmt_rating(row.rating.rating)
        spec_lbl = _spec_label(m.class_name, row.rating.spec)
        meta = " · ".join(x for x in (m.class_name, spec_lbl) if x)
        suffix = f" — _{meta}_" if meta else ""
        trend = f"  {_trend(row)}" if show_trend else ""
        lines.append(
            f"{medal} {emoji} **{name_link}**{crown} · `{rating}`{suffix}{trend}"
        )

    desc = "\n".join(lines) if lines else "Нет игроков под этот фильтр."
    embed = discord.Embed(title=_title(class_name, spec), description=desc, color=COLOR)
    shown = f"{start + 1}–{start + len(chunk)}" if chunk else "0"
    legend = "🔺 вверх · 🔻 вниз · 🆕 новичок · 👑 наш — " if show_trend else "👑 наш — "
    embed.set_footer(
        text=(
            f"{legend}стр. {page + 1}/{pages} · показаны {shown} из {total} · "
            f"в ростере {result.total_members} · метрика: UwU Best"
        )
    )
    return embed


# ---------------- интерактивные компоненты ----------------
class ClassSelect(discord.ui.Select):
    def __init__(self, parent: "LadderView"):
        self._parent = parent
        options = [discord.SelectOption(
            label="Все классы", value=ALL_OPT, default=parent.class_name is None,
        )]
        for c in CLASSES:
            options.append(discord.SelectOption(
                label=c, value=c, emoji=CLASS_EMOJI.get(c),
                default=(parent.class_name == c),
            ))
        super().__init__(
            placeholder="Класс…", min_values=1, max_values=1, options=options, row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        parent = self.view or self._parent
        if parent is None:
            await interaction.response.send_message(
                "Это сообщение устарело — вызови /ladder заново.", ephemeral=True,
            )
            return
        val = self.values[0]
        parent.class_name = None if val == ALL_OPT else val
        parent.spec = None
        parent.page = 0
        parent.rebuild()
        await interaction.response.edit_message(
            embed=parent.current_embed(), view=parent,
        )


class SpecSelect(discord.ui.Select):
    def __init__(self, parent: "LadderView"):
        self._parent = parent
        cls = parent.class_name
        if not cls:
            super().__init__(
                placeholder="Спек — сначала выбери класс",
                min_values=1, max_values=1, row=1, disabled=True,
                options=[discord.SelectOption(label="—", value="none")],
            )
            return
        options = [discord.SelectOption(
            label="Все спеки", value=ALL_OPT, default=parent.spec is None,
        )]
        for s in (1, 2, 3):
            options.append(discord.SelectOption(
                label=SPEC_NAMES.get(cls, {}).get(s, f"спек {s}"),
                value=str(s), default=(parent.spec == s),
            ))
        super().__init__(
            placeholder="Спек…", min_values=1, max_values=1, options=options, row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        parent = self.view or self._parent
        if parent is None:
            await interaction.response.send_message(
                "Это сообщение устарело — вызови /ladder заново.", ephemeral=True,
            )
            return
        val = self.values[0]
        parent.spec = None if val == ALL_OPT else int(val)
        parent.page = 0
        parent.rebuild()
        await interaction.response.edit_message(
            embed=parent.current_embed(), view=parent,
        )


class PrevButton(discord.ui.Button):
    def __init__(self, parent: "LadderView"):
        self._parent = parent
        super().__init__(
            label="◀", style=discord.ButtonStyle.secondary, row=2,
            disabled=parent.page <= 0,
        )

    async def callback(self, interaction: discord.Interaction):
        parent = self.view or self._parent
        if parent is None:
            await interaction.response.send_message(
                "Это сообщение устарело — вызови /ladder заново.", ephemeral=True,
            )
            return
        parent.page = max(0, parent.page - 1)
        parent.rebuild()
        await interaction.response.edit_message(
            embed=parent.current_embed(), view=parent,
        )


class NextButton(discord.ui.Button):
    def __init__(self, parent: "LadderView"):
        self._parent = parent
        super().__init__(
            label="▶", style=discord.ButtonStyle.secondary, row=2,
            disabled=parent.page >= parent.max_page(),
        )

    async def callback(self, interaction: discord.Interaction):
        parent = self.view or self._parent
        if parent is None:
            await interaction.response.send_message(
                "Это сообщение устарело — вызови /ladder заново.", ephemeral=True,
            )
            return
        parent.page = min(parent.max_page(), parent.page + 1)
        parent.rebuild()
        await interaction.response.edit_message(
            embed=parent.current_embed(), view=parent,
        )


class LadderView(discord.ui.View):
    def __init__(self, result: LadderResult, limit: int = 0, class_name: Optional[str] = None):
        super().__init__(timeout=300)
        self.result = result
        self.limit = limit
        self.class_name = class_name
        self.spec: Optional[int] = None
        self.page = 0
        self.message: Optional[discord.Message] = None
        self.rebuild()

    def _row_count(self) -> int:
        return len(_filter_rows(self.result, self.class_name, self.spec, self.limit))

    def max_page(self) -> int:
        return max(0, math.ceil(self._row_count() / PAGE_SIZE) - 1)

    def current_embed(self) -> discord.Embed:
        return render_embed(self.result, self.class_name, self.spec, self.page, self.limit)

    def rebuild(self):
        # клампим страницу и пересобираем компоненты (спек-меню зависит от класса)
        self.page = max(0, min(self.page, self.max_page()))
        self.clear_items()
        self.add_item(ClassSelect(self))
        self.add_item(SpecSelect(self))
        self.add_item(PrevButton(self))
        self.add_item(NextButton(self))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:  # noqa: BLE001
                pass


class LadderBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.cache = LadderCache(CONFIG)

    async def setup_hook(self):
        self.tree.add_command(roster_group)
        if CONFIG.discord_guild_id:
            guild = discord.Object(id=CONFIG.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Команды синхронизированы для сервера %s", CONFIG.discord_guild_id)
            # Чистим �����старевшие ГЛОБАЛЬНЫЕ команды (от прошлых версий/синков):
            # иначе в списке Discord висят дубли /ladder и команда вызывается дважды
            # (ошибки 40060 "already acknowledged" / 10062 "Unknown interaction").
            self.tree.clear_commands(guild=None)
            try:
                await self.tree.sync()
                log.info("Устаревшие глоба��ьные команды очищены (если были)")
            except discord.HTTPException as e:
                log.warning("Не удалось очистить глобальные команды: %s", e)
        else:
            await self.tree.sync()
            log.info("Команды синхронизированы глобально")

    async def on_ready(self):
        log.info("Вошёл как %s (id=%s)", self.user, self.user.id)


client = LadderBot()


async def _safe_send(interaction: discord.Interaction, **kwargs):
    """Ответ на /ladder. Если followup протух (долгая сборка → 404 Unknown Message),
    отправляем напрямую в канал, чтобы кнопки/пагинация всё равно работали."""
    try:
        return await interaction.followup.send(**kwargs)
    except discord.HTTPException as e:
        log.warning("followup.send не сработал (%s) — отправля�� напрямую в канал", e)
        try:
            await interaction.delete_original_response()
        except Exception:  # noqa: BLE001
            pass
        channel = interaction.channel
        if channel is not None:
            try:
                return await channel.send(**kwargs)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось отправить ладдер и в канал")
        return None


@client.tree.command(name="ladder", description="Показать ладдер гильдии")
async def ladder_cmd(interaction: discord.Interaction):
    log.info("Команда /ladder от %s", interaction.user)
    # Защищённый defer: если взаимодействие уже подтверждено/протухло — не падаем.
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
    except discord.HTTPException as e:
        log.warning("Не удалось отложить ответ (%s) — прерываю обработку", e)
        return
    try:
        result = await client.cache.get()
    except Exception as e:  # noqa: BLE001
        from ladder import APP_VERSION

        log.exception("Ошибка сборки ладдера")
        await _safe_send(
            interaction,
            content=f"❌ [ladder {APP_VERSION}] Не удалось собрать ладдер:\n```\n{str(e)[:1800]}\n```",
        )
        return

    view = LadderView(result)
    view.message = await _safe_send(interaction, embed=view.current_embed(), view=view)


@client.tree.command(name="runion", description="Что умеет бот и как им пользоваться")
async def runion_cmd(interaction: discord.Interaction):
    guild = f"{CONFIG.warmane_guild} @ {CONFIG.warmane_realm}"
    embed = discord.Embed(
        title="⛏️ Здарово, работяги!",
        description=(
            f"Это **ладдер-бот гильдии {guild}**.\n"
            f"Тяну свежие данные с **UwU Logs** (метрика **Best**) "
            f"и показываю **топ гильдии** прямо тут, в Discord."
        ),
        color=COLOR,
    )
    embed.add_field(
        name="📊  /ladder — весь топ гильдии",
        value=(
            "Просто вбей **`/ladder`** — и вот он, ладдер. Никаких настроек. 💪\n"
            "А под таблицей рулим кнопками:\n"
            "• 🎯 **Класс** — оставить один класс\n"
            "• 🌀 **Спек** — уточнить спек (напр. **топ Unholy DK**)\n"
            "• **◀ ▶** — листать страницы"
        ),
        inline=False,
    )
    embed.add_field(
        name="🧭  Расшифровка значков",
        value=(
            "🥇 🥈 🥉 — **топ-3** · 👑 — **наш человек**\n"
            "🔺N — **поднялся** · 🔻N — **упал** · 🆕 — **новичок** · ➖ — без движения"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠️  /roster — состав гильдии",
        value=(
            "• ➕ **`/roster add nick:<ник>`** — закинуть игрока *(может каждый!)*\n"
            "• ➖ **`/roster remove nick:<ник>`** — убрать *(только модеры)*\n"
            "• 📋 **`/roster list`** — сколько сейчас в ростере\n"
            "_Новые бойцы появятся в ладдере автоматически._"
        ),
        inline=False,
    )
    embed.add_field(
        name="ℹ️  /runion",
        value="Показать эту шпаргалку снова.",
        inline=False,
    )
    embed.set_footer(text="Создатель: Egormashina")
    await interaction.response.send_message(embed=embed)


# ---------------- /roster ----------------
roster_group = app_commands.Group(name="roster", description="Управление ростером")


def _can_manage(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


@roster_group.command(name="add", description="Добавить игрока в ростер")
@app_commands.describe(nick="Имя персонажа", char_class="Класс (для иконки)")
@app_commands.rename(char_class="class")
@app_commands.choices(char_class=[app_commands.Choice(name=c, value=c) for c in CLASSES])
async def roster_add(
    interaction: discord.Interaction,
    nick: str,
    char_class: Optional[app_commands.Choice[str]] = None,
):
    cls = char_class.value if char_class else ""
    try:
        added = roster.add_member(CONFIG.roster_file, nick, cls)
    except Exception as e:  # noqa: BLE001
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        return
    if added:
        client.cache.invalidate()
        extra = f" ({cls})" if cls else ""
        await interaction.response.send_message(
            f"✅ Добавлен **{nick}**{extra}. Появится в ладдере после `/ladder refresh:true`.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"ℹ️ **{nick}** уже в ростере.", ephemeral=True,
        )


@roster_group.command(name="remove", description="Убрать игрока из ростера")
@app_commands.describe(nick="Имя персонажа")
async def roster_remove(interaction: discord.Interaction, nick: str):
    if not _can_manage(interaction):
        await interaction.response.send_message(
            "⛔ Убирать игроков могут только модераторы (право «Управление сервером»).",
            ephemeral=True,
        )
        return
    try:
        removed = roster.remove_member(CONFIG.roster_file, nick)
    except Exception as e:  # noqa: BLE001
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        return
    if removed:
        client.cache.invalidate()
        await interaction.response.send_message(
            f"✅ Убран **{nick}** (бэкап в roster.txt.removed.txt).", ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"ℹ️ **{nick}** не найден в ростере.", ephemeral=True,
        )


@roster_group.command(name="list", description="Показать размер ростера")
async def roster_list(interaction: discord.Interaction):
    try:
        members = roster.load_local_roster(CONFIG.roster_file)
    except Exception as e:  # noqa: BLE001
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        return
    names = ", ".join(m.name for m in members[:40])
    more = "" if len(members) <= 40 else f" … (+{len(members) - 40})"
    await interaction.response.send_message(
        f"📋 В ростере **{len(members)}** игроков:\n{names}{more}", ephemeral=True,
    )


def main():
    from ladder import APP_VERSION

    log.info("RUnion Ladder Bot | %s | UWU_MODE=%s", APP_VERSION, CONFIG.uwu_mode)
    if not CONFIG.discord_token:
        raise SystemExit("Не задан DISCORD_TOKEN (см. .env)")
    client.run(CONFIG.discord_token)


if __name__ == "__main__":
    main()
