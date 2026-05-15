#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_team_names.py — Obtiene homeTeam/awayTeam para cada partido en momentum_raw.json.
Endpoint: /event/{id}  (liviano, solo metadatos del partido)
Output: lpf/team_names.json  { event_id: {home: name, away: name} }
"""

import json, time, random, sys
from pathlib import Path

RAW_PATH  = Path(__file__).parent / "momentum_raw.json"
OUT_PATH  = Path(__file__).parent / "team_names.json"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(400)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except json.JSONDecodeError:
            snippet = ""
            try:
                snippet = page.evaluate("document.body.innerText").strip()[:100]
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

    with open(RAW_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    result = {}
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} partidos ya procesados.")

    pending = [eid for eid in raw if eid not in result]
    print(f"Partidos a procesar: {len(pending)}")
    if not pending:
        print("Todo al dia.")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            locale="es-AR", viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        print("Conectando a SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        total = len(pending)
        for i, eid in enumerate(pending, 1):
            data = nav_json(page, f"https://api.sofascore.com/api/v1/event/{eid}")
            if data and "event" in data:
                ev = data["event"]
                result[eid] = {
                    "home": ev.get("homeTeam", {}).get("name", ""),
                    "away": ev.get("awayTeam", {}).get("name", ""),
                    "home_id": ev.get("homeTeam", {}).get("id"),
                    "away_id": ev.get("awayTeam", {}).get("id"),
                    "home_score": ev.get("homeScore", {}).get("current"),
                    "away_score": ev.get("awayScore", {}).get("current"),
                    "round": ev.get("roundInfo", {}).get("round"),
                }
                if i % 20 == 0 or i == total:
                    print(f"[{i}/{total}] {result[eid]['home']} vs {result[eid]['away']}")
                    with open(OUT_PATH, "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
            else:
                print(f"[{i}/{total}] MISS eid={eid}")
                result[eid] = {"home": None, "away": None}

            time.sleep(0.4 + random.random() * 0.4)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ok = sum(1 for v in result.values() if v["home"])
    print(f"\nListo. {ok}/{len(result)} partidos con nombres.")


if __name__ == "__main__":
    main()
