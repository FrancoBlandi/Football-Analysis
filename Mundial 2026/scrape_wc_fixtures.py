#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_fixtures.py — Fixture completo del Mundial 2026 (SofaScore)
Genera wc2026_fixtures.json con todos los partidos por fecha, grupo y equipos.

Uso:
    python "Mundial 2026/scrape_wc_fixtures.py"
"""

import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WC_SEASON_ID = 58210
OUT_PATH     = Path(__file__).parent / "wc2026_fixtures.json"
BASE         = "https://api.sofascore.com/api/v1"

GROUP_TOURNAMENT_IDS = {
    "A": 3954, "B": 3955, "C": 3956, "D": 3957,
    "E": 3958, "F": 3959, "G": 3960, "H": 3961,
    "I": 139403, "J": 139404, "K": 139405, "L": 139406,
}


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(600)
            return json.loads(page.evaluate("document.body.innerText"))
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def parse_event(e, group):
    home = e.get("homeTeam", {})
    away = e.get("awayTeam", {})
    status = e.get("status", {}).get("description", "")
    score_h = e.get("homeScore", {}).get("current")
    score_a = e.get("awayScore", {}).get("current")
    return {
        "event_id":   e.get("id"),
        "group":      group,
        "round":      e.get("roundInfo", {}).get("name", f"Grupo {group}"),
        "round_num":  e.get("roundInfo", {}).get("round"),
        "home_id":    home.get("id"),
        "home_name":  home.get("name"),
        "away_id":    away.get("id"),
        "away_name":  away.get("name"),
        "timestamp":  e.get("startTimestamp"),
        "status":     status,
        "score_home": score_h,
        "score_away": score_a,
        "venue":      e.get("venue", {}).get("city", {}).get("name") if e.get("venue") else None,
    }


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    all_fixtures = []
    fixtures_by_group = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-419", viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        for group, t_id in GROUP_TOURNAMENT_IDS.items():
            group_fixtures = []

            # Eventos ya jugados
            for page_num in range(5):
                url  = f"{BASE}/tournament/{t_id}/season/{WC_SEASON_ID}/events/last/{page_num}"
                data = nav_json(page, url)
                if not data or not data.get("events"):
                    break
                for e in data["events"]:
                    group_fixtures.append(parse_event(e, group))
                if not data.get("hasNextPage", False):
                    break
                time.sleep(0.4)

            # Eventos próximos
            for page_num in range(5):
                url  = f"{BASE}/tournament/{t_id}/season/{WC_SEASON_ID}/events/next/{page_num}"
                data = nav_json(page, url)
                if not data or not data.get("events"):
                    break
                for e in data["events"]:
                    group_fixtures.append(parse_event(e, group))
                if not data.get("hasNextPage", False):
                    break
                time.sleep(0.4)

            # Deduplicar por event_id
            seen = set()
            deduped = []
            for f in group_fixtures:
                if f["event_id"] not in seen:
                    seen.add(f["event_id"])
                    deduped.append(f)

            deduped.sort(key=lambda x: x["timestamp"] or 0)
            fixtures_by_group[group] = deduped
            all_fixtures.extend(deduped)
            n = len(deduped)
            print(f"  Grupo {group}: {n} partidos")
            time.sleep(0.5)

        browser.close()

    all_fixtures.sort(key=lambda x: x["timestamp"] or 0)

    # Agrupar por fecha de partido (round_num) para el modelo
    from collections import defaultdict
    by_date = defaultdict(list)
    for f in all_fixtures:
        key = (f["group"], f["round_num"])
        by_date[key].append(f)

    out = {
        "total":           len(all_fixtures),
        "fixtures":        all_fixtures,
        "by_group":        fixtures_by_group,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"\nTotal partidos: {len(all_fixtures)}")
    print(f"Guardado: {OUT_PATH}")

    # Preview
    from datetime import datetime, timezone
    print("\nPróximos 6 partidos:")
    import time as _time
    now_ts = _time.time()
    upcoming = sorted([f for f in all_fixtures if (f["timestamp"] or 0) > now_ts],
                      key=lambda x: x["timestamp"])[:6]
    for f in upcoming:
        dt = datetime.fromtimestamp(f["timestamp"], tz=timezone.utc).strftime("%d/%m %H:%M UTC")
        print(f"  [{f['group']}] {f['home_name']} vs {f['away_name']}  —  {dt}")


if __name__ == "__main__":
    main()
