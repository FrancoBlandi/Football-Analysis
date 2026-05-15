#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_momentum.py — Scrape momentum graph + match incidents para LPF 2026.

Para cada partido en form_data.json descarga:
  - /event/{id}/graph       → presión minuto a minuto (momentum signal)
  - /event/{id}/incidents   → goles, rojas, subs con minuto exacto

Output: lpf/momentum_raw.json

Uso:
    python lpf/scrape_momentum.py
    python lpf/scrape_momentum.py --test     # solo los primeros 3 partidos
    python lpf/scrape_momentum.py --resume   # continúa desde donde quedó
"""

import json, time, random, argparse, sys
from pathlib import Path

FORM_PATH     = Path(__file__).parent / "form_data.json"
SCHEDULE_PATH = Path(__file__).parent / "schedule_ids.json"
OUT_PATH      = Path(__file__).parent / "momentum_raw.json"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(500)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except json.JSONDecodeError:
            snippet = ""
            try:
                snippet = page.evaluate("document.body.innerText").strip()[:120]
            except Exception:
                pass
            if "429" in snippet or "rate" in snippet.lower():
                wait = 40 + attempt * 20
                print(f"    rate-limit — esperando {wait}s…")
                time.sleep(wait)
            else:
                time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def scrape_match(page, event_id):
    base = f"https://api.sofascore.com/api/v1/event/{event_id}"

    graph_data = nav_json(page, f"{base}/graph")
    time.sleep(0.4 + random.random() * 0.3)

    incidents_data = nav_json(page, f"{base}/incidents")
    time.sleep(0.4 + random.random() * 0.3)

    return {
        "event_id": event_id,
        "graph":     graph_data,
        "incidents": incidents_data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",   action="store_true", help="Solo 3 partidos")
    parser.add_argument("--resume", action="store_true", help="Continúa desde donde quedó")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    # Preferir schedule_ids.json (calendario completo) sobre form_data.json
    if SCHEDULE_PATH.exists():
        with open(SCHEDULE_PATH, encoding="utf-8") as f:
            schedule = json.load(f)
        event_ids = sorted(int(eid) for eid in schedule)
        print(f"Fuente: schedule_ids.json ({len(event_ids)} partidos)")
    else:
        with open(FORM_PATH, encoding="utf-8") as f:
            form = json.load(f)
        event_ids = sorted(set(
            m["event_id"]
            for p in form.values()
            for m in p.get("matches", [])
        ))
        print(f"Fuente: form_data.json ({len(event_ids)} partidos)")

    result = {}
    if OUT_PATH.exists() and args.resume:
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} partidos ya procesados.")

    pending = [eid for eid in event_ids if str(eid) not in result]
    if args.test:
        pending = pending[:3]

    print(f"Partidos a procesar: {len(pending)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print("Iniciando sesión en SofaScore…")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        # Verificar API
        test = nav_json(page, f"https://api.sofascore.com/api/v1/event/{event_ids[0]}/incidents")
        if test is None:
            print("ERROR: API no responde")
            browser.close()
            return
        print(f"API OK\n")

        total = len(pending)
        for i, eid in enumerate(pending, 1):
            print(f"[{i}/{total}] event_id={eid}", end=" … ")
            data = scrape_match(page, eid)

            has_graph = bool(data.get("graph"))
            has_inc   = bool(data.get("incidents"))
            print(f"graph={'OK' if has_graph else 'MISS'}  incidents={'OK' if has_inc else 'MISS'}")

            result[str(eid)] = data

            # Guardar cada 10 partidos
            if i % 10 == 0 or i == total:
                with open(OUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"  -> guardado ({len(result)} partidos)")

            time.sleep(0.5 + random.random() * 0.5)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ok_graph = sum(1 for v in result.values() if v.get("graph"))
    ok_inc   = sum(1 for v in result.values() if v.get("incidents"))
    print(f"\nListo. {len(result)} partidos | graph OK: {ok_graph} | incidents OK: {ok_inc}")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
