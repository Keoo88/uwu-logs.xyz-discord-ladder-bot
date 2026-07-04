"""Быстрая проверка API-режима UwU — без discord и без браузера.

Пробует несколько способов запроса к /character и печатает, какой работает
и какой рейтинг вышел. Запуск:
    python test_api.py Egortbeast Icecrown 2
"""
import asyncio
import sys
import time

import aiohttp

ENDPOINT = "https://uwu-logs.xyz/character"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def main(name, server, spec):
    payload = {"name": name, "server": server, "spec": str(spec)}
    xhr = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    print(f"Проверяю {name} @ {server}, spec={spec}\n")
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        strategies = [
            ("post_json", "POST", dict(json=payload, headers=xhr)),
            ("post_form", "POST", dict(data=payload, headers=xhr)),
            ("get_xhr", "GET", dict(params=payload, headers=xhr)),
        ]
        for strat, method, kw in strategies:
            t = time.time()
            try:
                if method == "POST":
                    async with s.post(ENDPOINT, timeout=30, **kw) as r:
                        status = r.status
                        data = await r.json(content_type=None)
                else:
                    async with s.get(ENDPOINT, timeout=30, **kw) as r:
                        status = r.status
                        data = await r.json(content_type=None)
            except Exception as e:
                print(f"[{strat}] ОШИБКА: {e}")
                continue
            dt = time.time() - t
            ok = isinstance(data, dict) and "overall_points" in data
            if ok:
                pts = data.get("overall_points")
                rank = data.get("overall_rank")
                rating = round(pts / 100.0, 2) if isinstance(pts, (int, float)) else "?"
                print(f"[{strat}] OK за {dt:.2f}с — overall_points={pts} -> рейтинг={rating}, rank={rank}")
            else:
                keys = list(data)[:8] if isinstance(data, dict) else str(type(data))
                print(f"[{strat}] status={status}, не тот JSON. ключи/тип={keys}")


if __name__ == "__main__":
    a = sys.argv[1:]
    nm = a[0] if len(a) > 0 else "Egortbeast"
    sv = a[1] if len(a) > 1 else "Icecrown"
    sp = a[2] if len(a) > 2 else "2"
    asyncio.run(main(nm, sv, sp))
