"""Конфигурация бота, читается из окружения / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> List[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def _int_list(value: str, default: List[int]) -> List[int]:
    parts = _split(value)
    if not parts:
        return default
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            pass
    return out or default


@dataclass
class Config:
    discord_token: str = os.getenv("DISCORD_TOKEN", "")
    discord_guild_id: int = int(os.getenv("DISCORD_GUILD_ID") or 0)

    warmane_guild: str = os.getenv("WARMANE_GUILD", "RUnion")
    warmane_realm: str = os.getenv("WARMANE_REALM", "Icecrown")
    uwu_server: str = os.getenv("UWU_SERVER", "Icecrown")

    raider_ranks: List[str] = field(
        default_factory=lambda: [r.lower() for r in _split(os.getenv("RAIDER_RANKS", ""))]
    )

    uwu_mode: str = os.getenv("UWU_MODE", "browser").strip().lower()
    uwu_specs: List[int] = field(
        default_factory=lambda: _int_list(os.getenv("UWU_SPECS", "1,2,3"), [1, 2, 3])
    )
    uwu_api_url: str = os.getenv("UWU_API_URL", "").strip()
    uwu_api_rating_path: List[str] = field(
        default_factory=lambda: _split(os.getenv("UWU_API_RATING_PATH", "").replace(".", ","))
    )
    uwu_api_dps_path: List[str] = field(
        default_factory=lambda: _split(os.getenv("UWU_API_DPS_PATH", "").replace(".", ","))
    )

    ladder_limit: int = int(os.getenv("LADDER_LIMIT", "50"))
    cache_ttl: int = int(os.getenv("CACHE_TTL", "3600"))
    uwu_request_delay: float = float(os.getenv("UWU_REQUEST_DELAY", "0.1"))
    # Сколько параллельных браузеров-воркеров (каждый — отдельный Chromium).
    uwu_concurrency: int = int(os.getenv("UWU_CONCURRENCY", "6"))
    # Общий лимит на сборку ладдера (сек), чтобы команда не висела вечно.
    build_timeout: int = int(os.getenv("BUILD_TIMEOUT", "420"))

    # Локальный ростер: список игроков (по одному на строку) в этом файле.
    roster_file: str = os.getenv("ROSTER_FILE", "roster.txt")

    # Автоудаление из roster.txt игроков без DPS-логов (хилы/танки) после сбора,
    # чтобы будущие прогоны были короче. По умолчанию ВЫКЛ (безопасно): включи
    # UWU_PRUNE_ROSTER=1. Работает только в API-режиме, удалённые пишутся в бэкап.
    prune_roster: bool = (
        os.getenv("UWU_PRUNE_ROSTER", "0").strip().lower() in ("1", "true", "yes", "on")
    )

    # Смарт-опрос спеков: тянуть рейтинг только по известному лучшему спеку
    # игрока (в 2-3 раза меньше запросов). Первый прогон и /ladder refresh:true — полный опрос.
    smart_specs: bool = (
        os.getenv("UWU_SMART_SPECS", "1").strip().lower() in ("1", "true", "yes", "on")
    )
    # Дисковый кэш: мгновенная отдача ладдера после перезапуска бота.
    disk_cache: bool = (
        os.getenv("UWU_DISK_CACHE", "1").strip().lower() in ("1", "true", "yes", "on")
    )
    ratings_cache_file: str = os.getenv("RATINGS_CACHE_FILE", "ratings_cache.json")
    bestspec_file: str = os.getenv("BEST_SPECS_FILE", "best_specs.json")
    history_file: str = os.getenv("LADDER_HISTORY_FILE", "ladder_history.json")
    history_keep: int = int(os.getenv("LADDER_HISTORY_KEEP", "20"))

    # Какие ранги считать raider+, если список не задан явно.
    default_rank_keywords: List[str] = field(
        default_factory=lambda: ["gm", "officer", "raider"]
    )

    def is_raider(self, rank_name: str) -> bool:
        rank = (rank_name or "").lower()
        if self.raider_ranks:
            return any(rank == r or r in rank for r in self.raider_ranks)
        return any(k in rank for k in self.default_rank_keywords)


CONFIG = Config()
