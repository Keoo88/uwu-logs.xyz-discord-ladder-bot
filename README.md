<p align="center">
  <img src="https://img.shields.io/badge/RUnion%20Ladder%20Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="RUnion Ladder Bot">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white&style=for-the-badge">
  <img src="https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white&style=for-the-badge">
  <img src="https://img.shields.io/badge/WoW-3.3.5%20WotLK-orange?style=for-the-badge">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge">
</p>

<h1 align="center">⛏️ RUnion Ladder Bot</h1>

<p align="center">
  <b>Discord-бот для рейтингов гильдии с UwU Logs.</b><br>
  <i>Builds a beautiful guild ladder in Discord with class/spec filters, pagination, and position trends.</i>
</p>

<p align="center">
  <a href="#english">English</a> ·
  <a href="#russian">Русский</a>
</p>

---

<a name="english"></a>
## English

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#project-structure">Structure</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#license">License</a>
</p>

### About

**RUnion Ladder Bot** pulls guild member ratings from **UwU Logs** and builds an interactive ladder inside Discord — with class/spec filters, pagination, position trends, and custom badges.

### Features

- 📊 **Guild ladder** sorted by UwU Logs rating (Best metric), best to worst.
- 🎯 **Interactive filters** inside the message: class filter, spec selector, pagination (25 per page) — no re-typing commands.
- 🏆 **Best spec selection:** all DPS specs are checked per player, the highest result is used.
- 🩸 **Hybrids included:** Blood DK, Feral Druid etc. make the ladder; pure healers/tanks are filtered out.
- 📈 **Position trends:** bot remembers previous rankings and shows who climbed/dropped/is new.
- 👑 **Named badges:** special nicks get a crown.
- 🗂️ **Roster management from Discord:** `/roster add | remove | list`.
- 🌐 **Multi-server:** commands can be registered across multiple Discord servers.
- 💾 **Disk cache:** instant ladder output, auto-rebuild on TTL and roster changes.
- ⚙️ **Two engines:** `api` (fast, recommended) and `browser` (headless).

### Screenshots

<p align="center">
  <img width="500" alt="/ladder" src="docs/ladder.png">
  <br>
  <i>/ladder — guild top with filters and pagination</i>
</p>

<p align="center">
  <img width="500" alt="/runion" src="docs/runion.png">
  <br>
  <i>/runion — welcome and help</i>
</p>

<a name="commands"></a>
### Commands

| Command | Description | Permissions |
|---|---|---|
| `/ladder` | Show guild ladder. Filters and pagination via buttons | everyone |
| `/runion` | Welcome + help with commands and badges | everyone |
| `/roster add nick:<name>` | Add a player to the roster | everyone |
| `/roster remove nick:<name>` | Remove a player from the roster | mods / admins (Manage Server) |
| `/roster list` | Show current roster size | everyone |

#### Ladder badges

| Badge | Meaning |
|---|---|
| 🥇 🥈 🥉 | Guild top-3 |
| 👑 | Named player (custom badge) |
| 🔺N | Climbed N positions |
| 🔻N | Dropped N positions |
| 🆕 | New in ladder |
| ➖ | No change |

Class icons: 💀 DK · 🌿 Druid · 🏹 Hunter · ❄️ Mage · 🔨 Paladin · 🙏 Priest · 🗡️ Rogue · ⚡ Shaman · 🔥 Warlock · ⚔️ Warrior

<a name="quick-start"></a>
### Quick Start

```bash
git clone https://github.com/Keoo88/uwu-logs.xyz-discord-ladder-bot.git
cd uwu-logs.xyz-discord-ladder-bot
pip install -r requirements.txt
cp .env.example .env
#  -> edit .env: set DISCORD_TOKEN, DISCORD_GUILD_ID
python -u -B bot.py
```

Expected output:
```
RUnion Ladder Bot | 2026-07-05.38-local ... | UWU_MODE=api
Commands synced for server <GUILD_ID>
Logged in as RUnion bot#1120 (id=...)
```

<a name="configuration"></a>
### Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | **Required.** Bot token from Developer Portal |
| `DISCORD_GUILD_ID` | — | Server ID(s) for instant commands. Multiple: `111,222`. Empty → global (up to 1hr) |
| `WARMANE_GUILD` | `RUnion` | Guild name |
| `WARMANE_REALM` | `Icecrown` | Realm name |
| `UWU_SERVER` | `Icecrown` | Realm for UwU Logs |
| `UWU_MODE` | `browser` | Engine: `api` (recommended) or `browser` |
| `UWU_SPECS` | `1,2,3` | Talent specs to check (best is taken) |
| `LADDER_LIMIT` | `50` | Default ladder rows |
| `CACHE_TTL` | `3600` | Cache TTL in seconds (1 hour) |
| `UWU_REQUEST_DELAY` | `1.0` | Delay between UwU requests (sec) |
| `UWU_CONCURRENCY` | `2` | Concurrent requests in `browser` mode |
| `UWU_API_CONCURRENCY` | `8` | Concurrent requests in `api` mode |
| `UWU_PRUNE_ROSTER` | `0` | `1` — auto-remove unfound players |

> Full list with comments in [`.env.example`](.env.example).

#### Roster

[`roster.txt`](roster.txt) — one player per line:
```
Name | Class      # class is optional, used for icon
Anatolevich | Warrior
Esno | Hunter
```

Lines starting with `#` and empty lines are ignored. Edit via Discord with `/roster add | remove`.

<a name="project-structure"></a>
### Project Structure

| File | Purpose |
|---|---|
| `bot.py` | Discord bot: commands, buttons, embeds |
| `ladder.py` | Ladder builder, cache, version |
| `uwu.py` | UwU Logs requests (api / browser), best spec |
| `roster.py` | Roster read/write |
| `store.py` | Disk cache, position history, best specs |
| `config.py` | Config from `.env` |
| `discover.py` | UwU API endpoint discovery helper |
| `test_api.py` | Quick API mode test |
| `roster.txt` | Player list |

<a name="faq"></a>
### FAQ

**`/ladder` shows old parameters.** Restart Discord client (Ctrl+R) to refresh command list.

**First ladder build is slow.** Full UwU scan (~3–4 min). Subsequent runs use cache; rebuild on TTL (1hr) and roster changes.

**`Expecting value: line 1 column 1` / empty responses.** UwU throttles under high load — keep `UWU_API_CONCURRENCY` at 8 or below.

**Player not in ladder.** Check nickname in `roster.txt` (case-sensitive, must match Warmane/UwU) and ensure they have DPS logs on UwU.

<a name="license"></a>
### License

MIT — do whatever you want, but credit the author.

Created by: **Egormashina**

---

<a name="russian"></a>
## Русский

<p align="center">
  <a href="#особенности">Особенности</a> ·
  <a href="#команды">Команды</a> ·
  <a href="#быстрый-старт">Быстрый старт</a> ·
  <a href="#настройка">Настройка</a> ·
  <a href="#устройство-проекта">Устройство</a> ·
  <a href="#faq-1">FAQ</a> ·
  <a href="#лицензия">Лицензия</a>
</p>

### Об аддоне

**RUnion Ladder Bot** тянет рейтинги игроков гильдии с **UwU Logs** и строит красивый ладдер прямо в Discord — с фильтрами по классу/спеку, листалкой и трендами позиций.

<a name="особенности"></a>
### Особенности

- 📊 **Ладдер гильдии** по рейтингу UwU Logs (метрика **Best**), от лучших к худшим.
- 🎯 **Интерактивные фильтры** прямо в сообщении: выбор класса, спека, листание страниц (по 25 строк) — без повторного ввода команды.
- 🏆 **Максимум по спекам:** для каждого игрока проверяются все ДПС-ветки и берётся лучший результат.
- 🩸 **Хибриды учитываются:** Blood DK, Feral Druid и подобные попадают в ладдер; чистые хилы/танки отсеиваются.
- 📈 **Тренды позиций:** бот запоминает прошлые места и показывает, кто поднялся/опустился/новичок.
- 👑 **Именные значки:** особые ники подсвечиваются короной.
- 🗂️ **Управление ростером из Discord:** `/roster add | remove | list`.
- 🌐 **Несколько серверов:** команды регистрируются сразу на нескольких Discord-серверах.
- 💾 **Дисковый кеш:** мгновенный вывод ладдера, авто-пересбор по TTL и после правок ростера.
- ⚙️ **Два движка сбора:** `api` (быстрый, рекомендуется) и `browser` (через headless-браузер).

### Скриншоты

<p align="center">
  <img width="500" alt="/ladder" src="docs/ladder.png">
  <br>
  <i>/ladder — топ гильдии с фильтрами и листалкой</i>
</p>

<p align="center">
  <img width="500" alt="/runion" src="docs/runion.png">
  <br>
  <i>/runion — приветствие и справка</i>
</p>

<a name="команды"></a>
### Команды

| Команда | Описание | Права |
|---|---|---|
| `/ladder` | Показать ладдер гильдии. Фильтры и листалка — кнопками | все |
| `/runion` | Приветствие + справка по командам и значкам | все |
| `/roster add nick:<ник>` | Добавить игрока в ростер | все |
| `/roster remove nick:<ник>` | Убрать игрока из ростера | модеры / админы (Manage Server) |
| `/roster list` | Сколько игроков в ростере | все |

#### Значки в ладдере

| Значок | Смысл |
|---|---|
| 🥇 🥈 🥉 | Топ-3 гильдии |
| 👑 | «Наш человек» (именной значок) |
| 🔺N | Поднялся на N позиций |
| 🔻N | Опустился на N позиций |
| 🆕 | Новичок в ладдере |
| ➖ | Без изменений |

Иконки классов: 💀 DK · 🌿 Druid · 🏹 Hunter · ❄️ Mage · 🔨 Paladin · 🙏 Priest · 🗡️ Rogue · ⚡ Shaman · 🔥 Warlock · ⚔️ Warrior

<a name="быстрый-старт"></a>
### Быстрый старт

```bash
git clone https://github.com/Keoo88/uwu-logs.xyz-discord-ladder-bot.git
cd uwu-logs.xyz-discord-ladder-bot
pip install -r requirements.txt
cp .env.example .env
#  -> открой .env и впиши DISCORD_TOKEN и DISCORD_GUILD_ID
python -u -B bot.py
```

В консоли должно появиться:
```
RUnion Ladder Bot | 2026-07-05.38-local ... | UWU_MODE=api
Команды синхронизированы для сервера <GUILD_ID>
Вошёл как RUnion bot#1120 (id=...)
```

<a name="настройка"></a>
### Настройка (`.env`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DISCORD_TOKEN` | — | **Обязательно.** Токен бота из Developer Portal |
| `DISCORD_GUILD_ID` | — | ID сервера(ов) для мгновенной регистрации. Несколько — через запятую (`111,222`). Пусто → глобально |
| `WARMANE_GUILD` | `RUnion` | Название гильдии |
| `WARMANE_REALM` | `Icecrown` | Реалм |
| `UWU_SERVER` | `Icecrown` | Реалм для UwU Logs |
| `UWU_MODE` | `browser` | Движок: `api` (рекомендуется) или `browser` |
| `UWU_SPECS` | `1,2,3` | Какие ветки талантов проверять |
| `LADDER_LIMIT` | `50` | Строк в ладдере по умолчанию |
| `CACHE_TTL` | `3600` | TTL кеша (1 час) |
| `UWU_REQUEST_DELAY` | `1.0` | Пауза между запросами к UwU (сек) |
| `UWU_CONCURRENCY` | `2` | Одновременные запросы в `browser`-режиме |
| `UWU_API_CONCURRENCY` | `8` | Одновременные запросы в `api`-режиме |
| `UWU_PRUNE_ROSTER` | `0` | `1` — авто-удалять ненайденных |

> Полный список с комментариями — в [`.env.example`](.env.example).

#### Ростер

Файл [`roster.txt`](roster.txt) — по одному игроку на строку:
```
Имя | Класс      # класс нужен только для иконки, можно не указывать
Anatolevich | Warrior
Esno | Hunter
```

Строки с `#` и пустые игнорируются. Ростер можно править из Discord через `/roster add | remove`.

<a name="устройство-проекта"></a>
### Устройство проекта

| Файл | Назначение |
|---|---|
| `bot.py` | Discord-бот: команды, кнопки, эмбеды |
| `ladder.py` | Сборка ладдера, кеш, версия |
| `uwu.py` | Запросы к UwU Logs (api / browser), лучший спек |
| `roster.py` | Чтение/запись ростера |
| `store.py` | Дисковый кеш, история позиций, лучшие спеки |
| `config.py` | Чтение настроек из `.env` |
| `discover.py` | Поиск API-эндпоинта UwU |
| `test_api.py` | Проверка API-режима |
| `roster.txt` | Список игроков гильдии |

<a name="faq-1"></a>
### Частые вопросы

**`/ladder` показывает старые параметры.** Перезапусти клиент Discord (Ctrl+R) — список команд обновится.

**Ladder долго собирается в первый раз.** Это нормально: полный скан UwU (~3–4 мин). Дальше из кеша мгновенно; пересбор — по TTL (1 ч) и после правок ростера.

**`Expecting value: line 1 column 1` / пустые ответы.** UwU троттлит при нагрузке — не поднимай `UWU_API_CONCURRENCY` выше 8.

**Игрока нет в ладдере.** Проверь ник в `roster.txt` (регистр как на Warmane/UwU) и что у него есть ДПС-логи на UwU.

<a name="лицензия"></a>
### Лицензия

MIT — делай что хочешь, но упоминай автора.

Создатель: **Egormashina**
