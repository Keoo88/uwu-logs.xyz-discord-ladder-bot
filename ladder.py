"""Ladder build: local roster (roster.txt) -> UwU ratings -> sorting.

Extras:
  * disk cache (instant answer after restart);
  * smart spec polling (only known best spec -> 2-3x fewer requests);
  * trends up/down vs previous build.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import Config
from roster import Member, load_local_roster, prune_members
from store import DiskStore
from uwu import RatingResult, fetch_best_ratings

log = logging.getLogger("ladder")

# Меняй при изменениях — по логу/ошибке видно, какая версия запущена.
APP_VERSION = "2026-07-04.36-local (calmer greeting, pickaxe icon)"


@dataclass
class LadderRow:
    rank: int
    member: Member
    rating: RatingResult
    prev_rank: Optional[int] = None


@dataclass
class LadderResult:
    rows: List[LadderRow]
    total_members: int
    raiders: int
    built_at: float


def _result_to_payload(result: "LadderResult", server: str) -> dict:
    return {
        "version": 1,
        "built_at": result.built_at,
        "server": server,
        "total_members": result.total_members,
        "rows": [
            {
                "rank": r.rank,
                "prev_rank": r.prev_rank,
                "name": r.member.name,
                "class": r.member.class_name,
                "rank_name": r.member.rank,
                "rating": r.rating.rating,
                "dps": r.rating.dps,
                "spec": r.rating.spec,
                "profile_url": r.rating.profile_url,
                "report_url": r.rating.report_url,
                "throttled": r.rating.throttled,
            }
            for r in result.rows
        ],
    }


def result_from_payload(data: dict) -> Optional["LadderResult"]:
    try:
        rows: List[LadderRow] = []
        for d in data.get("rows", []):
            member = Member(
                name=d["name"],
                class_name=d.get("class", ""),
                rank=d.get("rank_name", "Raider"),
            )
            res = RatingResult(
                name=d["name"],
                rating=d.get("rating"),
                dps=d.get("dps"),
                spec=d.get("spec"),
                report_url=d.get("report_url"),
                profile_url=d.get("profile_url", ""),
                throttled=d.get("throttled", False),
            )
            rows.append(LadderRow(
                rank=d.get("rank", len(rows) + 1),
                member=member,
                rating=res,
                prev_rank=d.get("prev_rank"),
            ))
        if not rows:
            return None
        return LadderResult(
            rows=rows,
            total_members=data.get("total_members", len(rows)),
            raiders=data.get("total_members", len(rows)),
            built_at=data.get("built_at", 0.0),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Битый дисковый кэш ладдера: %s", e)
        return None


async def build_ladder(cfg: Config, disk: DiskStore, full: bool = False) -> LadderResult:
    members = list(load_local_roster(cfg.roster_file))
    log.info("Игроков в ростере: %d (файл %s)", len(members), cfg.roster_file)

    preferred = {} if full else disk.load_best_specs()
    smart = bool(cfg.smart_specs) and not full
    if full:
        log.info("Полная пересборка (refresh) — опрашиваю все dps-спеки.")

    started = time.time()
    ratings = await asyncio.wait_for(
        fetch_best_ratings(
            cfg,
            [(m.name, m.class_name) for m in members],
            preferred_specs=preferred,
            smart=smart,
        ),
        timeout=cfg.build_timeout,
    )
    log.info("Сбор рейтингов занял %.1f сек", time.time() - started)

    # Автоотсев хилов/танков: удаляем тех, у кого НЕТ DPS-логов и кто НЕ был
    # придушен троттлом. Только в API-режиме.
    if cfg.prune_roster and cfg.uwu_mode == "api":
        prunable: List[str] = []
        skipped_throttled = 0
        for m in members:
            res = ratings.get(m.name)
            if res is None or res.rating is not None:
                continue
            if getattr(res, "throttled", False):
                skipped_throttled += 1
            else:
                prunable.append(m.name)
        if prunable:
            removed = prune_members(cfg.roster_file, prunable)
            log.info(
                "Найдено %d игроков без DPS-логов (хилы/танки) — удалены из %s. "
                "В следующий раз будет быстрее.",
                len(removed), cfg.roster_file,
            )
        else:
            log.info("Игроков без DPS-логов для удаления не найдено.")
        if skipped_throttled:
            log.info(
                "Пропущено %d None из-за троттла — НЕ удалены (проверю в следующий раз).",
                skipped_throttled,
            )

    prev_ranks = disk.previous_ranks()

    rows_data = []
    for m in members:
        res = ratings.get(m.name) or RatingResult(name=m.name)
        rows_data.append((m, res))

    # Сортировка: есть рейтинг -> по рейтингу desc, затем по dps desc; без данных — в конец.
    def sort_key(item):
        _, res = item
        has = res.rating is not None
        return (0 if has else 1, -(res.rating or 0), -(res.dps or 0))

    rows_data.sort(key=sort_key)

    rows = [
        LadderRow(
            rank=i + 1,
            member=m,
            rating=res,
            prev_rank=prev_ranks.get(m.name),
        )
        for i, (m, res) in enumerate(rows_data)
    ]
    result = LadderResult(
        rows=rows,
        total_members=len(members),
        raiders=len(members),
        built_at=time.time(),
    )

    # Обновляем известные лучшие спеки (не затирая тех, кого не опрашивали).
    try:
        best_specs = disk.load_best_specs()
        for _, res in rows_data:
            if res.rating is not None and res.spec:
                best_specs[res.name] = int(res.spec)
        disk.save_best_specs(best_specs)
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось обновить best_specs: %s", e)

    # Снимок для трендов + полный кэш на диск.
    try:
        cur_ranks = {r.member.name: r.rank for r in rows}
        cur_ratings = {
            r.member.name: r.rating.rating
            for r in rows if r.rating.rating is not None
        }
        disk.record_snapshot(cur_ranks, cur_ratings)
        disk.save_cache(_result_to_payload(result, cfg.uwu_server))
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось сохранить кэш/историю: %s", e)

    return result


class LadderCache:
    """TTL-кеш в памяти + подхват дискового кэша при старте."""

    def __init__(self, cfg: Config, disk: Optional[DiskStore] = None):
        self.cfg = cfg
        self.disk = disk or DiskStore(cfg)
        self._value: Optional[LadderResult] = None
        self._lock: Optional[asyncio.Lock] = None
        # Подхватываем прошлый ладдер с диска — /ladder ответит сразу после рестарта.
        data = self.disk.load_cache()
        if data:
            restored = result_from_payload(data)
            if restored:
                self._value = restored
                age = time.time() - restored.built_at
                log.info(
                    "Загрузил ладдер с диска (%d строк, возраст %.0f сек).",
                    len(restored.rows), age,
                )

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def invalidate(self) -> None:
        self._value = None

    async def get(self, force: bool = False) -> LadderResult:
        async with self._get_lock():
            fresh = (
                self._value is not None
                and (time.time() - self._value.built_at) < self.cfg.cache_ttl
            )
            if fresh and not force:
                age = time.time() - self._value.built_at
                log.info(
                    "Отдаю ладдер из кеша (возраст %.0f сек, TTL %d). refresh:true — пересобрать.",
                    age, self.cfg.cache_ttl,
                )
                return self._value
            log.info(
                "Кеш пуст или устарел — пересобираю ладдер%s",
                " (refresh, полный опрос)" if force else " (смарт-опрос)",
            )
            self._value = await build_ladder(self.cfg, self.disk, full=force)
            return self._value
