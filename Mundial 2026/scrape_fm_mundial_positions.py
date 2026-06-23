#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_fm_mundial_positions.py — Descarga posiciones de jugadores del FM Mundial 2026
Conecta al Chrome con CDP en puerto 9222 (ya logueado).
"""
import json, sys, io, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "fm_mundial_positions.json"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(600)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except Exception as e:
            print(f"  warn ({attempt+1}/{retries}): {e}")
            time.sleep(2 + attempt * 2)
    return None


def fetch_all_players(page):
    players = []
    limit   = 100
    offset  = 0

    # Intentar distintos endpoints conocidos del FM
    bases = [
        "https://vy5pw1hbv5.execute-api.us-east-1.amazonaws.com/prod/api/v1",
        "https://api.fantasymanager.ar/api/v1",
        "https://fantasymanager.ar/api/v1",
    ]

    base = None
    data = None
    for b in bases:
        url  = f"{b}/players/statistics/all?limit={limit}&offset=0&sort_stat=mean_points&sort_order=desc"
        print(f"Probando: {url}")
        data = nav_json(page, url)
        if data and ("players" in data or isinstance(data, list)):
            base = b
            print(f"  OK — base: {b}")
            break
        else:
            print(f"  No responde o sin jugadores")

    if not base or not data:
        print("ERROR: no se encontró endpoint válido")
        return []

    items = data.get("players", data) if isinstance(data, dict) else data
    players.extend(items)
    total_pages = data.get("totalPages", 1) if isinstance(data, dict) else 1
    print(f"Página 1/{total_pages} — {len(players)} jugadores")

    offset = limit
    page_n = 2
    while offset < total_pages * limit:
        url  = f"{base}/players/statistics/all?limit={limit}&offset={offset}&sort_stat=mean_points&sort_order=desc"
        d    = nav_json(page, url)
        if not d:
            print(f"  ERROR en página {page_n}, saltando")
        else:
            batch = d.get("players", d) if isinstance(d, dict) else d
            if not batch:
                break
            players.extend(batch)
            print(f"  Página {page_n}/{total_pages} — acum {len(players)}")
        offset += limit
        page_n += 1
        time.sleep(0.2)

    return players


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3)
    except Exception:
        sys.exit("Chrome CDP no disponible en puerto 9222")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx     = browser.contexts[0] if browser.contexts else browser.new_context()
        page    = ctx.new_page()

        # Primero ir a FM para tener sesión activa
        print("Navegando a FM para sesión...")
        page.goto("https://fantasymanager.ar/estadisticas", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1500)

        print("\nDescargando jugadores...")
        players = fetch_all_players(page)
        page.close()

    print(f"\nTotal: {len(players)} jugadores")
    if not players:
        print("Sin jugadores — verificar endpoint")
        return

    # Mostrar campos disponibles del primer jugador
    if players:
        print(f"\nCampos disponibles: {list(players[0].keys())}")

    # Extraer posiciones
    positions = {}
    for p in players:
        name = p.get("full_name") or p.get("name", "")
        pos  = (p.get("position") or p.get("pos") or p.get("role") or "?")
        team = (p.get("team") or {})
        team_name = team.get("name", "") if isinstance(team, dict) else str(team)
        pid  = p.get("id") or p.get("player_id")
        positions[str(pid)] = {"name": name, "position": pos, "team": team_name}

    # Guardar
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"players": players, "positions": positions}, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {OUT}")

    # Mostrar muestra
    print("\nMuestra posiciones:")
    sample_names = ["Kimmich","Grimaldo","Raphinha","Luis Diaz","Doku","Neymar","Araujo","Wirtz","Musiala","Messi","Haaland","degaard","Cancelo","Wesley","Perisic","Mahrez"]
    for pid, d in positions.items():
        if any(n.lower() in d["name"].lower() for n in sample_names):
            print(f"  {d['name']:30s} {d['team']:20s} pos={d['position']}")


if __name__ == "__main__":
    main()
