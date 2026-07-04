"""Дисковое хранилище: мгновенная отдача после рестарта + тренды.

Три JSON-файла (пути настраиваются в config):
  * ratings_cache.json  — последний собранный ладдер целиком. Загружается при
    старте бота, чтобы /ladder отвечал сразу, без пересборки.
  * best_specs.json     — {имя: лучший_спек}. Копится между запусками и позволяет
    «умному» опросу тянуть рейтинг только по реальному мейн-спеку.
  * ladder_history.json — компактные снимки прошлых сборок (ранги + рейтинги),
    чтобы показывать ↑/↓ позиций с прошлого раза.

Всё обёрнуто в try/except: проблемы с диском не должны ронять бота.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Dict, List, Optional

log = logging.getLogger("store")


def _read_json(path: str):
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось прочитать %s: %s", path, e)
        return None


def _write_json(path: str, obj) -> None:
    try:
        # Пишем во временный файл и атомарно заменяем — чтобы не оставить битый JSON.
        directory = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось записать %s: %s", path, e)


class DiskStore:
    def __init__(self, cfg):
        self.enabled = bool(getattr(cfg, "disk_cache", True))
        self.cache_path = getattr(cfg, "ratings_cache_file", "ratings_cache.json")
        self.bestspec_path = getattr(cfg, "bestspec_file", "best_specs.json")
        self.history_path = getattr(cfg, "history_file", "ladder_history.json")
        self.history_keep = max(1, int(getattr(cfg, "history_keep", 20)))

    # ---- полный кэш ладдера ----
    def load_cache(self) -> Optional[dict]:
        if not self.enabled:
            return None
        data = _read_json(self.cache_path)
        if isinstance(data, dict) and data.get("rows"):
            return data
        return None

    def save_cache(self, payload: dict) -> None:
        if not self.enabled:
            return
        _write_json(self.cache_path, payload)

    # ---- известные лучшие спеки (для смарт-опроса) ----
    def load_best_specs(self) -> Dict[str, int]:
        data = _read_json(self.bestspec_path)
        out: Dict[str, int] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    out[k] = int(v)
                except (TypeError, ValueError):
                    pass
        return out

    def save_best_specs(self, mapping: Dict[str, int]) -> None:
        if mapping:
            _write_json(self.bestspec_path, mapping)

    # ---- история для трендов ----
    def _snapshots(self) -> List[dict]:
        data = _read_json(self.history_path)
        if isinstance(data, dict) and isinstance(data.get("snapshots"), list):
            return data["snapshots"]
        return []

    def previous_ranks(self) -> Dict[str, int]:
        snaps = self._snapshots()
        if not snaps:
            return {}
        last = snaps[-1]
        ranks = last.get("ranks") if isinstance(last, dict) else None
        out: Dict[str, int] = {}
        if isinstance(ranks, dict):
            for k, v in ranks.items():
                try:
                    out[k] = int(v)
                except (TypeError, ValueError):
                    pass
        return out

    def record_snapshot(self, ranks: Dict[str, int], ratings: Dict[str, float]) -> None:
        snaps = self._snapshots()
        snaps.append({"at": time.time(), "ranks": ranks, "ratings": ratings})
        if len(snaps) > self.history_keep:
            snaps = snaps[-self.history_keep:]
        _write_json(self.history_path, {"version": 1, "snapshots": snaps})
