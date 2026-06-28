#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_fm_players.py — Descarga todos los jugadores de Fantasy Manager AR
y mapea mean_points / mvp a nuestros player_ids de SofaScore.

Uso:
    python lpf/scrape_fm_players.py
"""

import json, sys, io, time, unicodedata, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_BASE  = "https://vy5pw1hbv5.execute-api.us-east-1.amazonaws.com/prod/api/v1"
LPF_PATH  = Path(__file__).parent / "lpf_data.json"
OUT_FM    = Path(__file__).parent / "fm_players.json"
OUT_MAP   = Path(__file__).parent / "fm_mapped.json"


def normalize(s: str) -> str:
    """Minúsculas, sin tildes, sin puntuación."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(400)
            return json.loads(page.evaluate("document.body.innerText"))
        except Exception as e:
            print(f"  warn ({attempt+1}/{retries}): {e}")
            time.sleep(2 + attempt * 2)
    return None


def fetch_all_players(page):
    """Pagina por todos los jugadores del endpoint de FM."""
    players = []
    limit   = 50
    offset  = 0

    # Primera llamada para saber totalPages
    url  = f"{API_BASE}/players/statistics/all?limit={limit}&offset=0&sort_stat=mean_points&sort_order=desc"
    data = nav_json(page, url)
    if not data:
        print("ERROR: no response del API")
        return []

    total_pages = data.get("totalPages", 1)
    total_items = total_pages * limit
    print(f"  Total páginas: {total_pages} (~{total_items} jugadores)")

    players.extend(data.get("players", []))
    print(f"  Página 1/{total_pages} — {len(players)} jugadores")

    offset = limit
    page_n = 2
    while offset < total_pages * limit:
        url  = f"{API_BASE}/players/statistics/all?limit={limit}&offset={offset}&sort_stat=mean_points&sort_order=desc"
        data = nav_json(page, url)
        if not data:
            print(f"  ERROR en página {page_n}, saltando...")
        else:
            batch = data.get("players", [])
            players.extend(batch)
            print(f"  Página {page_n}/{total_pages} — acum {len(players)}")
            if not batch:
                break
        offset += limit
        page_n += 1
        time.sleep(0.3)

    return players


def map_to_sofascore(fm_players, lpf_data):
    """
    Mapea jugadores de FM a player_ids de SofaScore por nombre.
    Retorna dict: player_id → {fm_id, mean_points, mvp, fm_name, fm_team}
    """
    # Construir índice de nuestros jugadores: nombre_norm → player_id
    our_index = {}
    for p in lpf_data.get("Primera LPF 2026", []):
        pid  = p.get("player_id")
        name = p.get("Jugador", "")
        if pid and name:
            our_index[normalize(name)] = pid

    mapped   = {}
    unmatched = []

    for fp in fm_players:
        fname = fp.get("full_name", fp.get("name", ""))
        fnorm = normalize(fname)

        # Buscar match exacto primero
        pid = our_index.get(fnorm)

        # Si no, buscar por apellido (último token)
        if not pid:
            last = fnorm.split()[-1] if fnorm else ""
            candidates = [k for k in our_index if last in k.split()]
            if len(candidates) == 1:
                pid = our_index[candidates[0]]
            elif len(candidates) > 1:
                # Desambiguar por primer token
                first = fnorm.split()[0] if fnorm else ""
                for c in candidates:
                    if first in c.split():
                        pid = our_index[c]
                        break

        if pid:
            mapped[str(pid)] = {
                "fm_id":       fp.get("id"),
                "fm_name":     fname,
                "fm_team":     fp.get("team", {}).get("name", ""),
                "mean_points": fp.get("mean_points"),
                "mvp":         fp.get("mvp") or 0,
                "price":       fp.get("price"),
                "goals":       fp.get("goals") or 0,
                "assists":     fp.get("assists") or 0,
                "rating":      fp.get("rating"),
                "total_shots": fp.get("total_shots") or 0,
                "key_passes":  fp.get("key_passes") or 0,
            }
        else:
            unmatched.append(fname)

    return mapped, unmatched


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    print("=" * 60)
    print("Fantasy Manager AR — Descarga completa de jugadores")
    print("=" * 60)

    # Verificar que el port CDP esté disponible
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3)
        print("Chrome CDP disponible en puerto 9222.")
    except Exception:
        print("\nERROR: Chrome no está corriendo con --remote-debugging-port=9222")
        print("Corré primero: python lpf/scrape_bpr.py (y dejá Chrome abierto)")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx     = browser.contexts[0] if browser.contexts else browser.new_context()
        page    = ctx.new_page()

        print("\nDescargando todos los jugadores de FM...")
        fm_players = fetch_all_players(page)
        page.close()

    print(f"\nTotal jugadores FM descargados: {len(fm_players)}")

    # Guardar raw
    with open(OUT_FM, "w", encoding="utf-8") as f:
        json.dump(fm_players, f, ensure_ascii=False, indent=2)
    print(f"Raw guardado en {OUT_FM}")

    # Mapear a SofaScore IDs
    with open(LPF_PATH, encoding="utf-8") as f:
        lpf_data = json.load(f)

    mapped, unmatched = map_to_sofascore(fm_players, lpf_data)
    print(f"\nMapeados: {len(mapped)} | Sin match: {len(unmatched)}")

    if unmatched[:20]:
        print(f"Sin match (primeros 20): {unmatched[:20]}")

    # Top 20 por mean_points
    print("\nTop 20 por mean_points:")
    top = sorted(mapped.items(), key=lambda x: x[1]["mean_points"] or 0, reverse=True)[:20]
    for pid, d in top:
        print(f"  {d['fm_name']:<28} {d['fm_team']:<25} pts={d['mean_points']}  mvp={d['mvp']}")

    with open(OUT_MAP, "w", encoding="utf-8") as f:
        json.dump(mapped, f, ensure_ascii=False, indent=2)
    print(f"\nMapeado guardado en {OUT_MAP}")


if __name__ == "__main__":
    main()
