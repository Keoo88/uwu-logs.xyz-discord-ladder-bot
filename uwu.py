"""Клиент UwU Logs — тянет \"Best\"-рейтинг персонажа.

Режимы (UWU_MODE):
  * browser — грузит /character через СИНХРОННЫЙ Playwright в нескольких потоках.
    Каждый поток — свой браузер (свой user_data_dir), обрабатывает часть игроков.
    Синхронный API надёжнее async на Windows (async-в-потоке там любит виснуть).
  * api     — бьёт напрямую в JSON-эндпоинт (быстро). URL и пути к полям — из конфига.

Публичная точка входа: fetch_best_ratings(cfg, names) -> {имя: RatingResult}.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import random
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import quote

log = logging.getLogger("uwu")

UWU_BASE = "https://uwu-logs.xyz"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Шаблон вида "19.74 (19347)" — перцентиль и dps.
RATING_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*\(\s*([\d\s.,]+)\s*\)")


@dataclass
class RatingResult:
    name: str
    rating: Optional[float] = None      # перцентиль "Best" (больше = лучше)
    dps: Optional[float] = None         # абсолютный dps (внутреннее, в вывод не идёт)
    spec: Optional[int] = None          # на каком спеке найден лучший рейтинг
    report_url: Optional[str] = None    # ссылка на лучший лог (если найдена)
    profile_url: str = ""               # ссылка на профиль UwU
    throttled: bool = False             # True, если хоть один спек придушен троттлом

    @property
    def has_data(self) -> bool:
        return self.rating is not None or self.dps is not None


def character_url(name: str, server: str, spec: int) -> str:
    return f"{UWU_BASE}/character?name={quote(name)}&server={quote(server)}&spec={spec}"


def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    cleaned = str(raw).replace(" ", "").replace("\u00a0", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _dig(obj, path: List[str]):
    cur = obj
    for key in path:
        if isinstance(cur, list):
            try:
                cur = cur[int(key)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            if key not in cur:
                return None
            cur = cur[key]
        else:
            return None
    return cur


def _parse_rating_from_text(text: str):
    if not text:
        return None, None
    best_rating = None
    best_dps = None
    for m in RATING_RE.finditer(text):
        rating = _to_float(m.group(1))
        dps = _to_float(m.group(2))
        if rating is None:
            continue
        if best_rating is None or rating > best_rating:
            best_rating = rating
            best_dps = dps
    return best_rating, best_dps


# Порядок деревьев талантов 3.3.5 (спек 1/2/3) -> какие спеки ИМЕЮТ СМЫСЛ для dps-ладдера.
# Чисто хил/танк спеки не грузим вообще (экономит загрузки и время).
# Гибриды оставляем: Blood DK (танк+dd), Feral друид (кот/медведь) — dps на том же дереве.
DPS_SPECS_BY_CLASS = {
    "warrior": [1, 2],            # Arms, Fury (3 Prot — танк, пропуск)
    "paladin": [3],               # Ret (1 Holy, 2 Prot — пропуск)
    "hunter": [1, 2, 3],          # все dps
    "rogue": [1, 2, 3],           # все dps
    "priest": [3],               # Shadow (1 Disc, 2 Holy — пропуск)
    "death knight": [1, 2, 3],    # Blood/Frost/Unholy — Blood гибрид, оставляем всё
    "deathknight": [1, 2, 3],
    "dk": [1, 2, 3],
    "shaman": [1, 2],            # Ele, Enh (3 Resto — пропуск)
    "mage": [1, 2, 3],           # все dps
    "warlock": [1, 2, 3],         # все dps
    "druid": [1, 2],             # Balance, Feral (3 Resto — пропуск)
}


def specs_for_class(cfg, class_name: str) -> List[int]:
    """Спеки для загрузки под класс игрока (без чистых хил/танк деревьев)."""
    all_specs = cfg.uwu_specs or [1, 2, 3]
    if not class_name:
        return all_specs
    dps = DPS_SPECS_BY_CLASS.get(class_name.strip().lower())
    if dps is None:
        return all_specs  # незнакомый класс — грузим все спеки
    picked = [s for s in dps if s in all_specs]
    return picked or all_specs


def _specs_to_try(cfg, name, class_name, preferred, smart):
    """(спеки для первого прохода, все dps-спеки).

    В смарт-режиме первый проход ограничиваем известным лучшим спеком игрока —
    это в 2-3 раза меньше запросов. Если он не даст рейтинг, вызывающий код
    доопрашивает остальные (фолбэк), поэтому данные не теряются.
    """
    all_specs = specs_for_class(cfg, class_name)
    if smart and preferred:
        p = preferred.get(name)
        if p in all_specs:
            return [p], all_specs
    return all_specs, all_specs


def _norm_player(p):
    """Приводит игрока к паре (имя, класс). Принимает строку или кортеж."""
    if isinstance(p, str):
        return (p, "")
    name = p[0]
    class_name = p[1] if len(p) > 1 and p[1] else ""
    return (name, class_name)


# ---------------- публичная точка входа ----------------
async def fetch_best_ratings(cfg, players, preferred_specs=None, smart=False) -> Dict[str, RatingResult]:
    """Вернёт {имя: RatingResult} — лучший рейтинг среди dps-спеков игрока.

    players: список (имя, класс) или просто имён. Класс определяет, какие спеки
    вообще грузить (чисто хил/танк пропускаем).

    preferred_specs/smart: если smart=True, первый проход опрашивает только
    известный лучший спек игрока (в 2-3 раза меньше запросов), а None-случаи
    доопрашиваются по остальным спекам (фолбэк) — данные не теряются.
    """
    players = [_norm_player(p) for p in players]
    if not players:
        return {}
    preferred_specs = preferred_specs or {}
    if smart:
        log.info("UwU: смарт-опрос спеков включён (известных спеков: %d)", len(preferred_specs))
    if cfg.uwu_mode == "api":
        return await _fetch_ratings_api(cfg, players, preferred_specs, smart)
    # Синхронный Playwright в пуле потоков — весь блок уходит в отдельный поток,
    # чтобы не блокировать discord event loop.
    return await asyncio.to_thread(_run_browser_parallel, cfg, players, preferred_specs, smart)


# ---------------- browser (sync Playwright, пул потоков) ----------------
def _run_browser_parallel(cfg, players, preferred_specs=None, smart=False) -> Dict[str, RatingResult]:
    concurrency = max(1, cfg.uwu_concurrency)
    n_workers = min(concurrency, len(players))
    results: Dict[str, RatingResult] = {}
    if n_workers == 0:
        return results
    # Общая очередь задач: воркеры разбирают игроков по мере освобождения.
    # Так все браузеры заняты до самого конца (нет "хвоста" из одного воркера).
    task_q = queue.Queue()
    for player in players:
        task_q.put(player)
    log.info(
        "UwU: старт браузерного сбора — игроков=%d, воркеров=%d",
        len(players), n_workers,
    )
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = [
            ex.submit(_browser_worker, cfg, task_q, idx, preferred_specs, smart)
            for idx in range(n_workers)
        ]
        for fut in futures:
            try:
                results.update(fut.result())
            except Exception as e:  # noqa: BLE001
                log.exception("UwU: воркер завершился ошибкой: %s", e)
    log.info("UwU: сбор завершён, получено рейтингов=%d", len(results))
    return results


def _browser_worker(cfg, task_q, worker_idx: int, preferred_specs=None, smart=False) -> Dict[str, RatingResult]:
    from playwright.sync_api import sync_playwright

    headful = os.getenv("UWU_BROWSER_HEADFUL", "0").strip().lower() in ("1", "true", "yes")
    base_profile = os.getenv(
        "UWU_BROWSER_PROFILE", os.path.join(tempfile.gettempdir(), "uwu_pw_profile")
    )
    # Каждому воркеру — СВОЙ каталог профиля (persistent context блокирует папку).
    profile_dir = f"{base_profile}_{worker_idx}"
    results: Dict[str, RatingResult] = {}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=not headful,
            user_agent=UA,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            page = ctx.new_page()
            while True:
                try:
                    name, class_name = task_q.get_nowait()
                except queue.Empty:
                    break
                first, alls = _specs_to_try(cfg, name, class_name, preferred_specs, smart)
                res = _fetch_one_sync(cfg, page, name, first)
                if res.rating is None and len(first) < len(alls):
                    rest = [s for s in alls if s not in first]
                    res2 = _fetch_one_sync(cfg, page, name, rest)
                    if res2.rating is not None:
                        res = res2
                results[name] = res
        finally:
            ctx.close()
    return results


def _first_report_link_sync(page) -> Optional[str]:
    try:
        return page.eval_on_selector(
            "a[href*='report'], a[href*='/reports/']", "el => el.href"
        )
    except Exception:  # noqa: BLE001
        return None


# JS-проверка: в тексте страницы есть рейтинг вида "99.88 (19347)".
_HAS_RATING_JS = (
    r"/\d{1,3}(?:\.\d+)?\s*\(\s*[\d.,\s]+\s*\)/.test(document.body.innerText)"
)


def _load_spec(page, url):
    """Загрузить одну страницу спека → (rating, dps, report_url).

    Надёжное ожидание в две фазы, чтобы не читать пустую страницу под нагрузкой:
      1) дождаться, пока появится индикатор 'Loading raid data' ИЛИ сразу данные;
      2) дождаться, пока данные реально появятся (индикатор исчез + есть рейтинг).
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # фаза 1: дождаться начала загрузки или уже готовых данных
        try:
            page.wait_for_function(
                f"() => document.body.innerText.includes('Loading raid data') || {_HAS_RATING_JS}",
                timeout=8000,
            )
        except Exception:  # noqa: BLE001
            pass
        # фаза 2: дождаться реальных данных
        try:
            page.wait_for_function(
                f"() => !document.body.innerText.includes('Loading raid data') && {_HAS_RATING_JS}",
                timeout=15000,
            )
        except Exception:  # noqa: BLE001
            pass
        text = page.inner_text("body")
        report_url = _first_report_link_sync(page)
    except Exception as e:  # noqa: BLE001
        log.warning("UwU goto %s: %s", url, e)
        return None, None, None
    rating, dps = _parse_rating_from_text(text)
    return rating, dps, report_url


def _fetch_one_sync(cfg, page, name: str, specs: List[int]) -> RatingResult:
    best = RatingResult(
        name=name, profile_url=character_url(name, cfg.uwu_server, specs[0])
    )
    for spec in specs:
        url = character_url(name, cfg.uwu_server, spec)
        rating, dps, report_url = _load_spec(page, url)
        # Повтор только при реальном сбое загрузки (None). 0.0 — это ответ "нет данных
        # на этом спеке", повтор его не изменит, только замедлит сбор.
        if rating is None:
            rating, dps, report_url = _load_spec(page, url)
        # Валидным считаем только положительный рейтинг: 0.0 не должен побеждать пустой спек.
        if rating is None or rating <= 0:
            continue
        if best.rating is None or rating > best.rating:
            best = RatingResult(
                name=name, rating=rating, dps=dps, spec=spec,
                report_url=report_url, profile_url=url,
            )
        if cfg.uwu_request_delay > 0:
            time.sleep(cfg.uwu_request_delay)
    log.info("UwU %s -> rating=%s (спек %s)", name, best.rating, best.spec)
    return best


# ---------------- api (aiohttp, прямой JSON — без браузера) ----------------
# Эндпоинт данных персонажа. Отвечает JSON с overall_points/overall_rank/bosses.
UWU_CHAR_ENDPOINT = f"{UWU_BASE}/character"

# Рабочая стратегия запроса. post_json подтверждён test_api; можно переопределить env.
# Ставим её сразу (без фазы подбора) — иначе первая пачка параллельных запросов бьётся без ретраев.
_API_STRATEGY: str = os.getenv("UWU_API_STRATEGY", "post_json")

# Под нагрузкой сервер иногда отдаёт ПУСТОЕ тело (троттлинг) вместо JSON.
# Это НЕ "нет данных", а придушенный запрос — такие повторяем с backoff.
UWU_MAX_RETRIES = int(os.getenv("UWU_MAX_RETRIES", "5"))
UWU_RETRY_BASE_DELAY = float(os.getenv("UWU_RETRY_BASE_DELAY", "0.4"))
# Потолок паузы между ретраями — чтобы экспонента не раздувала хвост сбора.
UWU_RETRY_MAX_DELAY = float(os.getenv("UWU_RETRY_MAX_DELAY", "1.5"))


async def _one_request(session, strat: str, payload: dict, xhr: dict):
    """Один запрос выбранной стратегией.

    Возвращает (data, err):
      * (dict, None)      — распарсенный JSON;
      * (None, "empty")   — пустое тело: сервер придушил, СТОИТ повторить;
      * (None, Exception) — сетевая/иная ошибка: тоже стоит повторить.
    """
    try:
        if strat == "post_json":
            cm = session.post(UWU_CHAR_ENDPOINT, json=payload, headers=xhr, timeout=30)
        elif strat == "post_form":
            cm = session.post(UWU_CHAR_ENDPOINT, data=payload, headers=xhr, timeout=30)
        else:  # get_xhr
            cm = session.get(UWU_CHAR_ENDPOINT, params=payload, headers=xhr, timeout=30)
        async with cm as r:
            body = await r.text()
    except Exception as e:  # noqa: BLE001
        return None, e
    if not body or not body.strip():
        return None, "empty"
    try:
        return json.loads(body), None
    except Exception as e:  # noqa: BLE001
        return None, e


async def _request_char_json(session, name: str, server: str, spec: int, throttled: Optional[set] = None):
    """Дёргает /character стратегией _API_STRATEGY с ретраями.

    Пустое тело / сетевую ошибку считаем троттлингом и ПОВТОРЯЕМ с backoff.
    Валидный JSON без overall_points пока НЕ ретраим, но ЛОГИРУЕМ его форму —
    чтобы понять, это "нет данных" или тоже придушенный ответ.
    """
    payload = {"name": name, "server": server, "spec": str(spec)}
    xhr = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

    delay = UWU_RETRY_BASE_DELAY
    last_err = None
    for attempt in range(UWU_MAX_RETRIES + 1):
        data, err = await _one_request(session, _API_STRATEGY, payload, xhr)
        if isinstance(data, dict):
            if "overall_points" in data:
                return data
            # Диагностика: JSON есть, а overall_points нет. Покажем ключи и превью.
            log.info(
                "UwU api %s spec=%s: JSON без overall_points — ключи=%s превью=%.180r",
                name, spec, list(data.keys())[:8], data,
            )
            return None
        last_err = err
        if attempt < UWU_MAX_RETRIES:
            d = min(delay, UWU_RETRY_MAX_DELAY)
            await asyncio.sleep(d + random.uniform(0, d))
            delay *= 2
    log.warning(
        "UwU api %s spec=%s: пусто после %d попыток (%s)",
        name, spec, UWU_MAX_RETRIES + 1, last_err,
    )
    # Придушен троттлом — пометим (имя, спек), чтобы НЕ удалить игрока из ростера
    # по ошибке и чтобы повторить именно этот спек во втором проходе.
    if throttled is not None:
        throttled.add((name, spec))
    return None


def _rating_from_char(data) -> Optional[float]:
    """Best-рейтинг = overall_points / 100 (как отрисовано на сайте)."""
    pts = _to_float(data.get("overall_points")) if isinstance(data, dict) else None
    if pts is None:
        return None
    return round(pts / 100.0, 2)


async def _fetch_ratings_api(cfg, players, preferred_specs=None, smart=False) -> Dict[str, RatingResult]:
    import aiohttp

    results: Dict[str, RatingResult] = {}
    # У API-режима СВОЯ параллельность: сервер UwU троттлит при 20
    # (отдаёт пустые тела → потеря данных и длинный хвост). Поэтому по
    # умолчанию ограничиваем 8 (не трогая UWU_CONCURRENCY браузера).
    # Переопределяется явно через UWU_API_CONCURRENCY.
    api_conc = max(1, int(os.getenv(
        "UWU_API_CONCURRENCY", str(min(cfg.uwu_concurrency, 8))
    )))
    sem = asyncio.Semaphore(api_conc)
    log.info(
        "UwU: старт API-сбора — игроков=%d, параллельно=%d",
        len(players), api_conc,
    )
    # Плоский список задач (игрок, спек): семафор всегда занят полезной
    # работой, а не простаивает, пока один игрок ПОСЛЕДОВАТЕЛЬНО опрашивает свои специи.
    preferred_specs = preferred_specs or {}
    best: Dict[str, RatingResult] = {}
    throttled_pairs: set = set()   # (имя, спек), где ответ пришёл пустым (троттл)
    retry_throttled: set = set()   # (имя, спек), не восстановившиеся во 2-м проходе
    tasks_spec: List[tuple] = []
    all_specs_by_name: Dict[str, List[int]] = {}
    partial_names: set = set()   # опрошен только известный спек (смарт) — возможен фолбэк
    for (name, class_name) in players:
        first, alls = _specs_to_try(cfg, name, class_name, preferred_specs, smart)
        all_specs_by_name[name] = alls
        if len(first) < len(alls):
            partial_names.add(name)
        best[name] = RatingResult(
            name=name, profile_url=character_url(name, cfg.uwu_server, first[0]),
        )
        for spec in first:
            tasks_spec.append((name, spec))
    if smart:
        log.info(
            "UwU: смарт — первый проход %d (игрок,спек) вместо %d",
            len(tasks_spec), sum(len(v) for v in all_specs_by_name.values()),
        )

    def _apply(name: str, spec: int, data) -> None:
        """Обновляет best[name], если спек дал валидный положительный рейтинг."""
        if not data:
            return
        rating = _rating_from_char(data)
        # Валидным считаем только положительный рейтинг: 0.0 — это "нет данных".
        if rating is None or rating <= 0:
            return
        rank = _to_float(data.get("overall_rank"))
        cur = best[name]
        if cur.rating is None or rating > cur.rating:
            best[name] = RatingResult(
                name=name, rating=rating, dps=rank, spec=spec,
                profile_url=character_url(name, cfg.uwu_server, spec),
            )

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}, timeout=timeout) as session:
        async def fetch_one(name: str, spec: int):
            async with sem:
                data = await _request_char_json(
                    session, name, cfg.uwu_server, spec, throttled_pairs
                )
            # Задержку между запросами убрали: семафор уже ограничивает нагрузку.
            _apply(name, spec, data)

        await asyncio.gather(*(fetch_one(n, s) for (n, s) in tasks_spec))

        # Смарт-фолбэк: если у игрока опросили только известный спек, а он дал None
        # (сменил спек / лог протух), доопрашиваем остальные dps-спеки — чтобы не
        # потерять данные. Троттл-случаи чинит отдельный второй проход ниже.
        if smart and partial_names:
            fb_tasks: List[tuple] = []
            for name in partial_names:
                if best[name].rating is not None:
                    continue
                tried = preferred_specs.get(name)
                for spec in all_specs_by_name.get(name, []):
                    if spec != tried:
                        fb_tasks.append((name, spec))
            if fb_tasks:
                log.info("UwU: смарт-фолбэк — доопрашиваю %d (игрок,спек)", len(fb_tasks))
                await asyncio.gather(*(fetch_one(n, s) for (n, s) in fb_tasks))

        # Второй проход ТОЛЬКО по придушенным (имя, спек): их мало, а нагрузка уже
        # спала, поэтому повторяем с маленькой параллельностью. Это чинит случай,
        # когда ЛУЧШИЙ спек игрока был придушен и рейтинг вышел заниженным/пустым.
        if throttled_pairs:
            log.info(
                "UwU: второй проход по %d придушенным запросам",
                len(throttled_pairs),
            )
            sem2 = asyncio.Semaphore(3)

            async def retry_one(name: str, spec: int):
                async with sem2:
                    data = await _request_char_json(
                        session, name, cfg.uwu_server, spec, retry_throttled
                    )
                _apply(name, spec, data)

            await asyncio.gather(
                *(retry_one(n, s) for (n, s) in sorted(throttled_pairs))
            )

    # Осталось придушено даже после 2-го прохода: такие None НЕЛЬЗЯ удалять из
    # ростера — пустой ответ мог быть троттлом, а не подтверждённым "нет DPS-логов".
    still_throttled = {n for (n, _s) in retry_throttled}
    for name in still_throttled:
        if name in best and best[name].rating is None:
            best[name].throttled = True

    for name, res in best.items():
        results[name] = res
        log.info("UwU %s -> rating=%s (спек %s)", name, res.rating, res.spec)
    log.info("UwU: API-сбор завершён, получено рейтингов=%d", len(results))
    return results
