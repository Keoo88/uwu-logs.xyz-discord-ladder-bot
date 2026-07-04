"""Разведчик внутреннего API UwU Logs.

Открывает страницу персонажа в headless-браузере и для динамических эндпоинтов
(всё, кроме /static/) печатает: МЕТОД + полный URL + ТЕЛО ЗАПРОСА +
ключевые заголовки + начало тела ответа. Так видно, КАК дёргать эндпоинт напрямую.

Запуск:
    python discover.py Egortbeast Icecrown 2
"""
import asyncio
import sys

from playwright.async_api import async_playwright

BASE = "https://uwu-logs.xyz/character"


async def main(name: str, server: str, spec: str):
    url = BASE + "?name=" + name + "&server=" + server + "&spec=" + spec
    print("Открываю:", url, "\n")
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(resp):
            u = resp.url
            if "/static/" in u:
                return  # статика (иконки/предметы) — неинтересно
            ctype = resp.headers.get("content-type", "")
            req = resp.request
            try:
                body = await resp.text()
            except Exception:
                body = "<не удалось прочитать тело>"
            try:
                headers = req.headers
            except Exception:
                headers = {}
            interesting = {
                k: v for k, v in headers.items()
                if k.lower() in ("content-type", "x-requested-with", "accept")
            }
            captured.append({
                "method": req.method,
                "url": u,
                "status": resp.status,
                "ctype": ctype,
                "post_data": req.post_data,
                "headers": interesting,
                "body": body,
            })

        page.on("response", on_response)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        body_text = await page.inner_text("body")
        await browser.close()

    print("===== ДИНАМИЧЕСКИЕ ЗАПРОСЫ (без /static/) =====")
    for c in captured:
        print("\n--- " + c["method"] + " " + c["url"]
              + "  [status " + str(c["status"]) + ", " + c["ctype"] + "]")
        if c["headers"]:
            print("    заголовки:", c["headers"])
        if c["post_data"]:
            print("    ТЕЛО ЗАПРОСА:", c["post_data"][:600])
        else:
            print("    тело запроса: <нет, обычный GET>")
        head = c["body"][:700] if "json" in c["ctype"] else c["body"][:150]
        print("    ответ (начало):", head)

    print("\n===== ТЕКСТ СТРАНИЦЫ (для browser-режима) =====")
    print(body_text[:1200])


if __name__ == "__main__":
    a = sys.argv[1:]
    nm = a[0] if len(a) > 0 else "Egortbeast"
    sv = a[1] if len(a) > 1 else "Icecrown"
    sp = a[2] if len(a) > 2 else "2"
    asyncio.run(main(nm, sv, sp))
