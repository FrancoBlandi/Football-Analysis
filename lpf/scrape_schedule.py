#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_schedule.py — Obtiene todos los event IDs del calendario LPF 2026.
Endpoint: /tournament/155/season/87913/matches/round/{n}
Output: lpf/schedule_ids.json  — lista completa de event IDs
"""

import json, time, sys
from pathlib import Path

TOURNAMENT_ID = 155
SEASON_ID     = 87913
ROUNDS        = range(1, 17)   # fechas 1-16
OUT_PATH      = Path(__file__).parent / "schedule_ids.json"


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
                print(f"  rate-limit {wait}s...")
                time.sleep(wait)
            else:
                time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"  warn ({attempt+1}): {e}")
            time.sleep(3)
    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright && playwright install chromium")

    all_ids = {}   # event_id -> {round, home, away, status}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        print("Conectando a SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        for rnd in ROUNDS:
            url  = f"https://api.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/round/{rnd}"
            data = nav_json(page, url)

            if not data or "events" not in data:
                print(f"  Fecha {rnd:2d}: sin datos")
                continue

            events = data["events"]
            finished = [e for e in events if e.get("status", {}).get("type") == "finished"]

            for e in finished:
                eid = str(e["id"])
                all_ids[eid] = {
                    "round": rnd,
                    "home":  e.get("homeTeam", {}).get("name", ""),
                    "away":  e.get("awayTeam", {}).get("name", ""),
                    "home_score": e.get("homeScore", {}).get("current"),
                    "away_score": e.get("awayScore", {}).get("current"),
                }

            print(f"  Fecha {rnd:2d}: {len(finished)}/{len(events)} partidos terminados")
            time.sleep(0.6)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_ids, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(all_ids)} partidos en {OUT_PATH}")

    # Mostrar cuales faltan en momentum_raw.json
    raw_path = Path(__file__).parent / "momentum_raw.json"
    if raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            raw = json.load(f)
        missing = [eid for eid in all_ids if eid not in raw]
        print(f"Ya en momentum_raw: {len(raw)}")
        print(f"Faltan scrapear:    {len(missing)}")


if __name__ == "__main__":
    main()
