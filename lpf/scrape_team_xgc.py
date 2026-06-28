#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_team_xgc.py — xGC por equipo para LPF Apertura 2026
Genera lpf/team_xgc.json con expected goals concedidos calculados
a partir de shots against por zona + big chances against.
"""

import json, time, sys
from pathlib import Path

JSON_PATH = Path(__file__).parent / "lpf_data.json"
OUT_PATH  = Path(__file__).parent / "team_xgc.json"
TOURNAMENT_ID = 155
SEASON_ID     = 87913

FIXTURE_CLUBS = {
    "CA Talleres", "Club Atlético Belgrano", "Boca Juniors", "Huracán",
    "Argentinos Juniors", "CA Lanús", "Independiente Rivadavia",
    "Club Atlético Unión de Santa Fe", "Rosario Central", "CA Independiente",
    "Estudiantes de La Plata", "Racing Club", "River Plate", "San Lorenzo",
    "Vélez Sarsfield", "Gimnasia y Esgrima",
}


def compute_xgc(stats):
    """
    xGC = bigChancesAgainst × 0.35
          + (shotsFromInsideTheBoxAgainst − bigChancesAgainst) × 0.08
          + shotsFromOutsideTheBoxAgainst × 0.035
    """
    big     = stats.get("bigChancesAgainst") or 0
    inside  = stats.get("shotsFromInsideTheBoxAgainst") or 0
    outside = stats.get("shotsFromOutsideTheBoxAgainst") or 0
    return round(big * 0.35 + max(inside - big, 0) * 0.08 + outside * 0.035, 2)


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(500)
            return json.loads(page.evaluate("document.body.innerText"))
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(2 + attempt * 2)
    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with open(JSON_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    # Construir mapa club → club_id
    club_ids = {}
    for p in raw["Primera LPF 2026"]:
        club = p.get("Club")
        cid  = p.get("club_id")
        if club in FIXTURE_CLUBS and cid and club not in club_ids:
            club_ids[club] = cid

    result = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        for club, cid in sorted(club_ids.items()):
            url  = (f"https://api.sofascore.com/api/v1/team/{cid}"
                    f"/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/statistics/overall")
            data = nav_json(page, url)
            if not data or "statistics" not in data:
                print(f"  ERROR: {club} — no stats")
                continue

            stats   = data["statistics"]
            matches = stats.get("matches") or 1
            gc      = stats.get("goalsConceded") or 0
            xgc     = compute_xgc(stats)

            result[club] = {
                "club_id":    cid,
                "matches":    matches,
                "gc":         gc,
                "gc_pg":      round(gc  / matches, 3),
                "xgc":        xgc,
                "xgc_pg":     round(xgc / matches, 3),
                "big_chances_against":    stats.get("bigChancesAgainst") or 0,
                "shots_inside_against":   stats.get("shotsFromInsideTheBoxAgainst") or 0,
                "shots_outside_against":  stats.get("shotsFromOutsideTheBoxAgainst") or 0,
                "shots_on_target_against": stats.get("shotsOnTargetAgainst") or 0,
                "clean_sheets":           stats.get("cleanSheets") or 0,
            }
            print(f"  {club:<35} gc_pg={result[club]['gc_pg']:.2f}  xgc_pg={result[club]['xgc_pg']:.2f}  matches={matches}")
            time.sleep(0.5)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado en {OUT_PATH} — {len(result)} equipos")
    print("\nComparación GC real vs xGC (por partido):")
    for club, d in sorted(result.items(), key=lambda x: x[1]["xgc_pg"]):
        diff = round(d["xgc_pg"] - d["gc_pg"], 2)
        flag = "↑ suerte defensiva" if diff > 0.3 else ("↓ mala suerte" if diff < -0.3 else "")
        print(f"  {club:<35} gc={d['gc_pg']:.2f}  xgc={d['xgc_pg']:.2f}  diff={diff:+.2f}  {flag}")


if __name__ == "__main__":
    main()
