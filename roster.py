"""Локальный ростер: список игроков читается из текстового файла.

Формат (roster.txt), один персонаж на строку:
    Egortbeast | Mage        # имя | класс (класс нужен только для иконки)
    Somechar                 # можно просто имя
Пустые строки и строки, начинающиеся с #, игнорируются.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

log = logging.getLogger("roster")


@dataclass
class Member:
    name: str
    class_name: str = ""


def load_local_roster(path: str) -> List[Member]:
    if not os.path.exists(path):
        raise RuntimeError(
            f"Файл ростера не найден: {path}. Создай его и впиши игроков "
            f"(по одному на строку). Пример строки: 'Egortbeast | Mage'"
        )
    members: List[Member] = []
    seen = set()
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            name = parts[0]
            if not name:
                continue
            class_name = parts[1] if len(parts) > 1 and parts[1] else ""
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            members.append(Member(name=name, class_name=class_name))
    if not members:
        raise RuntimeError(
            f"В файле ростера {path} нет ни одного игрока. Впиши имена (по одному на строку)."
        )
    return members


def prune_members(path: str, names_to_remove, reason: str = "нет DPS-логов") -> List[str]:
    """Удаляет из ростера строки игроков из names_to_remove (регистронезависимо).

    Комментарии и пустые строки сохраняются. Удалённые строки дописываются в
    бэкап <path>.removed.txt с меткой времени — на случай, если игрок вернётся
    в DPS-спеке и его нужно будет вернуть вручную. Возвращает список удалённых имён.
    """
    remove = {str(n).strip().lower() for n in names_to_remove if str(n).strip()}
    if not remove or not os.path.exists(path):
        return []

    kept_lines: List[str] = []
    removed_raw: List[str] = []
    removed_names: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                kept_lines.append(raw.rstrip("\n"))
                continue
            name = line.split("|")[0].strip()
            if name and name.lower() in remove:
                removed_raw.append(raw.rstrip("\n"))
                removed_names.append(name)
            else:
                kept_lines.append(raw.rstrip("\n"))

    if not removed_names:
        return []

    # Бэкап удалённых строк (append), чтобы можно было вернуть вручную.
    import datetime
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    backup = path + ".removed.txt"
    try:
        with open(backup, "a", encoding="utf-8") as bf:
            bf.write(f"# удалены {stamp} ({reason})\n")
            for r in removed_raw:
                bf.write(r + "\n")
    except OSError as e:  # noqa: BLE001
        log.warning("Не удалось записать бэкап удалённых игроков в %s: %s", backup, e)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept_lines))
        if kept_lines:
            f.write("\n")

    log.info(
        "Из ростера %s удалено %d игроков без DPS-логов (бэкап: %s)",
        path, len(removed_names), backup,
    )
    return removed_names


def add_member(path: str, name: str, class_name: str = "") -> bool:
    """Добавляет игрока в ростер. Возвращает True, если добавлен, False — если уже был."""
    name = (name or "").strip()
    if not name:
        return False
    lower = name.lower()
    lines: List[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#"):
                    if line.split("|")[0].strip().lower() == lower:
                        return False  # уже есть
                lines.append(raw.rstrip("\n"))
    entry = name if not class_name else f"{name} | {class_name}"
    lines.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
    log.info("В ростер %s добавлен игрок: %s", path, name)
    return True


def remove_member(path: str, name: str) -> bool:
    """Убирает игрока из ростера вручную. Возвращает True, если был удалён."""
    removed = prune_members(path, [name], reason="удалён вручную")
    return bool(removed)
