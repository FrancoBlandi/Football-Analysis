#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
explore_wc2026.py — Exploración de SofaScore para Mundial 2026
Busca si existe sección de equipos/jugadores convocados al Mundial 2026.
"""

import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT_PATH = Path(__file__).parent / "wc2026_explore.json"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(700)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def try_endpoint(page, url, label):
    print(f"\n  [{label}]")
    print(f"  URL: {url}")
    data = nav_json(page, url)
    if data is None:
        print(f"  → sin respuesta / error")
        return None
    if isinstance(data, dict) and "error" in data:
        print(f"  → error: {data['error']}")
        return None
    # Preview primeros 300 chars
    preview = json.dumps(data, ensure_ascii=False)[:300]
    print(f"  → OK  preview: {preview}")
    return data


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    results = {}

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
        print("Iniciando sesión en SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        print(f"OK — {page.url}\n")

        print("=" * 65)
        print("1. BÚSQUEDA — 'world cup 2026' y variantes")
        print("=" * 65)

        search_queries = ["world cup 2026", "fifa world cup", "mundial 2026"]
        for q in search_queries:
            import urllib.parse
            enc = urllib.parse.quote(q)
            data = try_endpoint(page, f"https://api.sofascore.com/api/v1/search/all?q={enc}", f"search: {q}")
            if data:
                results[f"search_{q}"] = data
            time.sleep(0.8)

        print("\n" + "=" * 65)
        print("2. TORNEOS — IDs conocidos del Mundial FIFA")
        print("=" * 65)

        # FIFA WC 2022 era unique-tournament ID 16
        # Probamos IDs cercanos y candidatos para 2026
        wc_candidates = {
            16:   "FIFA WC (ID historico 2022)",
            17:   "Candidato WC 2026 A",
            336:  "Candidato WC 2026 B",
            480:  "Candidato WC 2026 C",
            681:  "Candidato WC 2026 D",
            1005: "Candidato WC 2026 E",
            1010: "Candidato WC 2026 F",
        }

        for tid, label in wc_candidates.items():
            data = try_endpoint(page, f"https://api.sofascore.com/api/v1/unique-tournament/{tid}", label)
            if data:
                results[f"tournament_{tid}"] = data
                # Si parece Mundial, explorar más
                name = (data.get("uniqueTournament") or {}).get("name", "")
                if "world" in name.lower() or "mundial" in name.lower() or "fifa" in name.lower() or "cup" in name.lower():
                    print(f"  ★ COINCIDENCIA: '{name}' — explorando temporadas...")
                    seasons = try_endpoint(page, f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/seasons", f"seasons of {tid}")
                    if seasons:
                        results[f"tournament_{tid}_seasons"] = seasons
                        # Buscar la temporada 2026
                        for s in (seasons.get("seasons") or [])[:10]:
                            sid  = s.get("id")
                            name_s = s.get("name", "")
                            year = s.get("year", "")
                            print(f"      Season: id={sid}  name={name_s}  year={year}")
                            if "2026" in str(year) or "2026" in str(name_s):
                                print(f"      ★ Temporada 2026 encontrada! id={sid}")
                                # Explorar equipos/grupos de esta temporada
                                groups = try_endpoint(page, f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/groups", f"groups season {sid}")
                                teams  = try_endpoint(page, f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/teams", f"teams season {sid}")
                                squad  = try_endpoint(page, f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/squads", f"squads season {sid}")
                                if groups: results[f"wc2026_groups"] = groups
                                if teams:  results[f"wc2026_teams"]  = teams
                                if squad:  results[f"wc2026_squads"] = squad
            time.sleep(0.6)

        print("\n" + "=" * 65)
        print("3. SELECCIONES — Argentina y otras (verificar si tienen sección WC26)")
        print("=" * 65)

        # IDs de selecciones en SofaScore
        national_teams = {
            3:    "Argentina",
            11:   "Brasil",
            6:    "Francia",
            9:    "España",
            4782: "Estados Unidos",
            100:  "Mexico",
        }

        for team_id, name in national_teams.items():
            print(f"\n  --- {name} (id={team_id}) ---")
            # Torneos del equipo → buscar si aparece un torneo "Mundial 2026"
            data = try_endpoint(page, f"https://api.sofascore.com/api/v1/team/{team_id}/unique-tournaments", f"{name} torneos")
            if data:
                results[f"national_{team_id}_tournaments"] = data
                tours = data.get("uniqueTournaments") or []
                for t in tours:
                    tname = t.get("name", "")
                    if "world" in tname.lower() or "mundial" in tname.lower() or "cup" in tname.lower() or "2026" in tname:
                        print(f"  ★ torneo relevante: {tname} (id={t.get('id')})")

            # Próximo evento — si tienen fixture en el Mundial
            next_ev = try_endpoint(page, f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0", f"{name} próximo evento")
            if next_ev:
                events = next_ev.get("events") or []
                for e in events[:3]:
                    tour_name = e.get("tournament", {}).get("name", "?")
                    home = e.get("homeTeam", {}).get("name", "?")
                    away = e.get("awayTeam", {}).get("name", "?")
                    ts   = e.get("startTimestamp")
                    print(f"    próximo: {home} vs {away} | torneo: {tour_name} | ts={ts}")
                    if "world" in tour_name.lower() or "mundial" in tour_name.lower() or "2026" in tour_name:
                        print(f"    ★ EVENTO MUNDIAL 2026 ENCONTRADO!")
                        results[f"wc2026_event_{e.get('id')}"] = e

            time.sleep(0.7)

        print("\n" + "=" * 65)
        print("4. ENDPOINT DIRECTO — /world-cup si existe en la API")
        print("=" * 65)

        misc_endpoints = [
            ("https://api.sofascore.com/api/v1/world-cup/2026",          "world-cup/2026"),
            ("https://api.sofascore.com/api/v1/world-cup/2026/squads",   "squads"),
            ("https://api.sofascore.com/api/v1/world-cup/2026/groups",   "groups"),
            ("https://api.sofascore.com/api/v1/world-cup/squads",        "world-cup/squads"),
            ("https://api.sofascore.com/api/v1/tournament/world-cup",    "tournament/world-cup"),
        ]
        for url, label in misc_endpoints:
            data = try_endpoint(page, url, label)
            if data and "error" not in data:
                results[f"misc_{label}"] = data
            time.sleep(0.5)

        browser.close()

    # Guardar resultados
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\nResultados guardados en {OUT_PATH}")
    print(f"Secciones con datos: {list(results.keys())}")


if __name__ == "__main__":
    main()
