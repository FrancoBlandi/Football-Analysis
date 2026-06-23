#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_lineups.py — Lineups probables/confirmados por fecha del Mundial 2026

Corre el día previo o el día del partido para cada jornada.
SofaScore publica lineups probables con anticipación y confirmados ~1h antes.

Impacto en el modelo:
  Titular confirmado  → P(over60) = 0.92
  Banco confirmado    → P(over60) = 0.08
  No en el partido    → P(over60) = 0.02
  Sin datos (default) → usa avg_mins_gm del club (comportamiento original)

Uso:
    python "Mundial 2026/scrape_wc_lineups.py" --fecha 1
    python "Mundial 2026/scrape_wc_lineups.py" --fecha 2
    python "Mundial 2026/scrape_wc_lineups.py"          # todas las fechas disponibles
"""

import json, time, sys, io, argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FIXTURES_PATH = Path(__file__).parent / "wc2026_fixtures.json"
OUT_PATH      = Path(__file__).parent / "wc2026_lineups.json"
BASE          = "https://api.sofascore.com/api/v1"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(500)
            return json.loads(page.evaluate("document.body.innerText"))
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def parse_lineups(event_id, data):
    """
    Parsea el response de /event/{id}/lineups.
    Devuelve dict: player_id → {"status": "starter"|"substitute"|"missing", "team": ..., "jersey": ...}
    """
    result = {}
    if not data:
        return result

    for side in ("home", "away"):
        side_data = data.get(side) or {}
        team_name = side_data.get("team", {}).get("name", "?")

        # Titulares
        for p in (side_data.get("players") or []):
            player = p.get("player") or {}
            pid    = player.get("id")
            if not pid:
                continue
            result[pid] = {
                "status":  "starter",
                "team":    team_name,
                "jersey":  p.get("jerseyNumber"),
                "pos":     p.get("position") or player.get("position", ""),
                "name":    player.get("name") or player.get("shortName", ""),
            }

        # Suplentes
        for p in (side_data.get("supportStaff") or []):
            pass  # staff no nos interesa

        for p_list_key in ("substitutes", "bench"):
            for p in (side_data.get(p_list_key) or []):
                player = p.get("player") or {}
                pid    = player.get("id")
                if not pid:
                    continue
                # No sobreescribir si ya está como starter
                if pid not in result:
                    result[pid] = {
                        "status":  "substitute",
                        "team":    team_name,
                        "jersey":  p.get("jerseyNumber"),
                        "pos":     p.get("position") or player.get("position", ""),
                        "name":    player.get("name") or player.get("shortName", ""),
                    }

        # Missing / bajas
        for p in (side_data.get("missingPlayers") or []):
            player = p.get("player") or {}
            pid    = player.get("id")
            if pid and pid not in result:
                result[pid] = {
                    "status":  "missing",
                    "team":    team_name,
                    "reason":  p.get("type") or p.get("reason", ""),
                    "name":    player.get("name") or player.get("shortName", ""),
                }

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", type=int, default=None,
                        help="Número de fecha de grupos (1, 2 o 3). Sin argumento: todas.")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures_data = json.load(f)

    all_fixtures = fixtures_data.get("fixtures", [])
    if args.fecha:
        all_fixtures = [f for f in all_fixtures if f.get("round_num") == args.fecha]

    # Cargar lineups existentes para no perder datos previos
    existing = {}
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    print(f"Partidos a revisar: {len(all_fixtures)}"
          f"{'  (fecha '+str(args.fecha)+')' if args.fecha else ''}")

    all_lineups = dict(existing)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-419", viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        for fx in all_fixtures:
            eid       = fx.get("event_id")
            home      = fx.get("home_name", "?")
            away      = fx.get("away_name", "?")
            group     = fx.get("group", "?")
            round_num = fx.get("round_num", "?")

            print(f"\n  [Gr {group} · F{round_num}] {home} vs {away}  (id={eid})")

            data = nav_json(page, f"{BASE}/event/{eid}/lineups")
            if not data or "error" in data:
                print(f"    → sin lineup disponible aún")
                time.sleep(0.5)
                continue

            # Detectar si son confirmados o probables
            confirmed = data.get("confirmed", False)
            label     = "CONFIRMADO" if confirmed else "probable"
            players   = parse_lineups(eid, data)

            starters  = [p for p in players.values() if p["status"] == "starter"]
            subs      = [p for p in players.values() if p["status"] == "substitute"]
            missing   = [p for p in players.values() if p["status"] == "missing"]

            print(f"    → [{label}]  {len(starters)} titulares · {len(subs)} suplentes · {len(missing)} bajas")

            for p in sorted(starters, key=lambda x: x.get("jersey") or 99):
                print(f"       ✓ #{str(p.get('jersey','?')):>2}  {p['name']:<28} ({p['team']})")
            if missing:
                for p in missing:
                    print(f"       ✗ {p['name']} ({p.get('reason','baja')})")

            all_lineups[str(eid)] = {
                "event_id":  eid,
                "home":      home,
                "away":      away,
                "group":     group,
                "round_num": round_num,
                "confirmed": confirmed,
                "players":   {str(k): v for k, v in players.items()},
            }

            time.sleep(0.5)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_lineups, f, ensure_ascii=False, indent=2)

    # Resumen
    events_with_data = [v for v in all_lineups.values() if v.get("players")]
    confirmed_count  = sum(1 for v in events_with_data if v.get("confirmed"))
    total_players    = sum(len(v.get("players", {})) for v in events_with_data)
    starters_total   = sum(
        sum(1 for p in v.get("players", {}).values() if p.get("status") == "starter")
        for v in events_with_data
    )

    print(f"\n{'='*55}")
    print(f"Lineups guardados: {len(events_with_data)} partidos")
    print(f"  Confirmados: {confirmed_count}  |  Probables: {len(events_with_data)-confirmed_count}")
    print(f"  Jugadores registrados: {total_players}  ({starters_total} titulares)")
    print(f"Guardado en: {OUT_PATH}")


if __name__ == "__main__":
    main()
