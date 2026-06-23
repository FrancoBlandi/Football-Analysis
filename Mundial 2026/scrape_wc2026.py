#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc2026.py — Mundial 2026 | SofaScore
Extrae grupos, equipos y plantillas convocadas del Mundial 2026.

unique-tournament ID : 16  (FIFA World Cup)
season ID            : 58210 (World Cup 2026)

Uso:
    python "Mundial 2026/scrape_wc2026.py"
    python "Mundial 2026/scrape_wc2026.py" --squads   # también baja plantillas
"""

import json, time, sys, io, argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WC_TOURNAMENT_ID = 16
WC_SEASON_ID     = 58210

BASE = "https://api.sofascore.com/api/v1"

OUT_DIR      = Path(__file__).parent
GROUPS_PATH  = OUT_DIR / "wc2026_groups.json"
TEAMS_PATH   = OUT_DIR / "wc2026_teams.json"
SQUADS_PATH  = OUT_DIR / "wc2026_squads.json"

# Grupos con sus tournament IDs internos (obtenidos en exploración)
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
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def fetch_group_teams(page, group_letter, tournament_id):
    """Obtiene los equipos de un grupo via standings."""
    # Opcion 1: standings del grupo
    url = f"{BASE}/tournament/{tournament_id}/season/{WC_SEASON_ID}/standings/total"
    data = nav_json(page, url)
    if data and "standings" in data:
        rows = []
        for standing in data["standings"]:
            for row in standing.get("rows", []):
                team = row.get("team", {})
                rows.append({
                    "id":        team.get("id"),
                    "name":      team.get("name"),
                    "shortName": team.get("shortName"),
                    "country":   team.get("country", {}).get("name", ""),
                    "group":     group_letter,
                })
        return rows

    # Opcion 2: events del grupo para inferir equipos
    url2 = f"{BASE}/tournament/{tournament_id}/season/{WC_SEASON_ID}/events/last/0"
    data2 = nav_json(page, url2)
    if data2 and "events" in data2:
        seen = {}
        for e in data2["events"]:
            for side in ("homeTeam", "awayTeam"):
                t = e.get(side, {})
                tid = t.get("id")
                if tid and tid not in seen:
                    seen[tid] = {
                        "id":        tid,
                        "name":      t.get("name"),
                        "shortName": t.get("shortName"),
                        "country":   t.get("country", {}).get("name", ""),
                        "group":     group_letter,
                    }
        return list(seen.values())

    return []


def fetch_squad(page, team_id, team_name):
    """Intenta obtener la plantilla convocada al Mundial 2026."""
    # Endpoint 1: squad específico del torneo/temporada
    url1 = f"{BASE}/team/{team_id}/unique-tournament/{WC_TOURNAMENT_ID}/season/{WC_SEASON_ID}/squad"
    data = nav_json(page, url1)
    if data and "players" in data:
        return data["players"], "tournament_squad"

    # Endpoint 2: squad general del equipo
    url2 = f"{BASE}/team/{team_id}/players"
    data2 = nav_json(page, url2)
    if data2 and "players" in data2:
        return data2["players"], "general_squad"

    return [], "not_found"


def parse_player(entry, group, team_name, team_id):
    p = entry.get("player", entry)  # algunos endpoints wrappean en "player"
    return {
        "id":       p.get("id"),
        "name":     p.get("name"),
        "shortName": p.get("shortName"),
        "position": p.get("position", {}).get("name") if isinstance(p.get("position"), dict) else p.get("position"),
        "age":      p.get("age"),
        "country":  p.get("country", {}).get("name") if isinstance(p.get("country"), dict) else "",
        "team":     team_name,
        "team_id":  team_id,
        "group":    group,
        "jerseyNumber": entry.get("jerseyNumber") or p.get("shirtNumber"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--squads", action="store_true", help="Bajar plantillas de cada selección")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-419",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        print("Iniciando en SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        # ── 1. Equipos por grupo ──────────────────────────────────────────────
        print("\n" + "="*60)
        print("PASO 1 — Distribución por grupos")
        print("="*60)

        all_teams_by_group = {}
        all_teams_flat     = []

        for group_letter, t_id in GROUP_TOURNAMENT_IDS.items():
            print(f"\n  Grupo {group_letter} (tournament_id={t_id})...")
            teams = fetch_group_teams(page, group_letter, t_id)

            if not teams:
                print(f"    → sin datos de standings/eventos aún")
            else:
                print(f"    → {len(teams)} equipos")
                for t in teams:
                    print(f"       {t['name']}")

            all_teams_by_group[group_letter] = teams
            all_teams_flat.extend(teams)
            time.sleep(0.7)

        # Fallback: si los standings no tienen datos, usar la lista de 48 equipos ya conocida
        if not all_teams_flat:
            print("\n  Standings vacíos — usando lista de 48 equipos scrapeada (sin grupos confirmados)")
            all_teams_flat = TEAMS_KNOWN

        # Guardar grupos
        with open(GROUPS_PATH, "w", encoding="utf-8") as f:
            json.dump({"groups": all_teams_by_group, "teams": all_teams_flat}, f, ensure_ascii=False, indent=2)
        print(f"\n  Guardado: {GROUPS_PATH}")

        # ── 2. Resumen por grupo ──────────────────────────────────────────────
        print("\n" + "="*60)
        print("RESUMEN — Equipos por grupo")
        print("="*60)
        for g, teams in all_teams_by_group.items():
            names = ", ".join(t["name"] for t in teams) if teams else "(pendiente)"
            print(f"  Grupo {g}: {names}")

        # ── 3. Plantillas (opcional) ──────────────────────────────────────────
        if args.squads:
            print("\n" + "="*60)
            print("PASO 2 — Plantillas convocadas")
            print("="*60)

            # Tomar la lista de equipos conocida (puede estar vacía si standings no cargaron)
            teams_to_scrape = all_teams_flat if all_teams_flat else TEAMS_KNOWN
            # Deduplicar por id
            seen_ids = set()
            unique_teams = []
            for t in teams_to_scrape:
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    unique_teams.append(t)

            all_squads = {}
            for t in unique_teams:
                team_id   = t["id"]
                team_name = t["name"]
                group     = t.get("group", "?")
                print(f"\n  [{group}] {team_name} (id={team_id})...")
                players, source = fetch_squad(page, team_id, team_name)
                parsed = [parse_player(e, group, team_name, team_id) for e in players]
                all_squads[team_name] = {
                    "team_id":  team_id,
                    "group":    group,
                    "source":   source,
                    "players":  parsed,
                }
                n = len(parsed)
                print(f"    → {n} jugadores ({source})")
                if n and n <= 30:
                    for p in parsed:
                        pos = p.get("position") or "?"
                        age = p.get("age") or "?"
                        print(f"       #{str(p.get('jerseyNumber','?')):>2}  {p['name']:<28} {str(pos or '?'):<12} edad={age}")
                time.sleep(0.8)

            with open(SQUADS_PATH, "w", encoding="utf-8") as f:
                json.dump(all_squads, f, ensure_ascii=False, indent=2)
            print(f"\n  Guardado: {SQUADS_PATH}")

            # Resumen disponibilidad
            found    = sum(1 for v in all_squads.values() if v["players"])
            notfound = len(all_squads) - found
            print(f"\n  Plantillas con datos: {found}/{len(all_squads)}")
            if notfound:
                missing = [k for k, v in all_squads.items() if not v["players"]]
                print(f"  Sin datos: {', '.join(missing)}")

        browser.close()

    print("\nListo.")


# Lista de 48 equipos conocidos (fallback cuando standings no tienen datos)
TEAMS_KNOWN = [
    {"id": 4758, "name": "Egypt",                "group": "?"},
    {"id": 4753, "name": "Cabo Verde",           "group": "?"},
    {"id": 4717, "name": "Belgium",              "group": "?"},
    {"id": 4757, "name": "Ecuador",              "group": "?"},
    {"id": 4778, "name": "Morocco",              "group": "?"},
    {"id": 4789, "name": "Paraguay",             "group": "?"},
    {"id": 4695, "name": "Scotland",             "group": "?"},
    {"id": 4739, "name": "Senegal",              "group": "?"},
    {"id": 4475, "name": "Norway",               "group": "?"},
    {"id": 4764, "name": "Ghana",                "group": "?"},
    {"id": 4698, "name": "Spain",                "group": "?"},
    {"id": 4741, "name": "Australia",            "group": "?"},
    {"id": 4736, "name": "South Africa",         "group": "?"},
    {"id": 4700, "name": "Turkey",               "group": "?"},
    {"id": 4725, "name": "Uruguay",              "group": "?"},
    {"id": 4688, "name": "Sweden",               "group": "?"},
    {"id": 4834, "name": "Saudi Arabia",         "group": "?"},
    {"id": 4819, "name": "Argentina",            "group": "?"},
    {"id": 4704, "name": "Portugal",             "group": "?"},
    {"id": 4752, "name": "Canada",               "group": "?"},
    {"id": 4729, "name": "Tunisia",              "group": "?"},
    {"id": 4479, "name": "Bosnia & Herzegovina", "group": "?"},
    {"id": 4766, "name": "Iran",                 "group": "?"},
    {"id": 4705, "name": "Netherlands",          "group": "?"},
    {"id": 4792, "name": "Qatar",                "group": "?"},
    {"id": 4770, "name": "Japan",                "group": "?"},
    {"id": 5164, "name": "Panama",               "group": "?"},
    {"id": 4715, "name": "Croatia",              "group": "?"},
    {"id": 4735, "name": "South Korea",          "group": "?"},
    {"id": 4691, "name": "Algeria",              "group": "?"},
    {"id": 4481, "name": "France",               "group": "?"},
    {"id": 4724, "name": "USA",                  "group": "?"},
    {"id": 4718, "name": "Austria",              "group": "?"},
    {"id": 4771, "name": "Jordan",               "group": "?"},
    {"id": 4767, "name": "Iraq",                 "group": "?"},
    {"id": 4711, "name": "Germany",              "group": "?"},
    {"id": 4723, "name": "Uzbekistan",           "group": "?"},
    {"id": 55827,"name": "Curacao",              "group": "?"},
    {"id": 7229, "name": "Haiti",                "group": "?"},
    {"id": 4823, "name": "DR Congo",             "group": "?"},
    {"id": 4784, "name": "New Zealand",          "group": "?"},
    {"id": 4699, "name": "Switzerland",          "group": "?"},
    {"id": 4781, "name": "Mexico",               "group": "?"},
    {"id": 4714, "name": "Czechia",              "group": "?"},
    {"id": 4713, "name": "England",              "group": "?"},
    {"id": 4768, "name": "Cote d'Ivoire",        "group": "?"},
    {"id": 4748, "name": "Brazil",               "group": "?"},
    {"id": 4820, "name": "Colombia",             "group": "?"},
]


if __name__ == "__main__":
    main()
