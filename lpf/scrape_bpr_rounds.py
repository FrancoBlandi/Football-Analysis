#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_bpr_rounds.py — BPR por fecha via delta entre rondas
Para cada ronda, descarga mvp acumulado y detecta quién subió → fue BPR esa fecha.
Genera lpf/bpr_rounds.json: fm_player_id → {bpr1, bpr2, bpr3, total_pts, appearances}

BPR pts: pos1=3, pos2=2, pos3=1
Requiere Chrome con --remote-debugging-port=9222
"""

import json, sys, io, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_BASE = "https://vy5pw1hbv5.execute-api.us-east-1.amazonaws.com/prod/api/v1"
CDP_URL  = "http://127.0.0.1:9222"
FM_PATH  = Path(__file__).parent / "fm_players.json"
OUT_PATH = Path(__file__).parent / "bpr_rounds.json"

BPR_PTS = {1: 3, 2: 2, 3: 1}


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(400)
            return json.loads(page.evaluate("document.body.innerText"))
        except Exception as e:
            print(f"  warn: {e}")
            time.sleep(2 + attempt * 2)
    return None


def fetch_mvp_snapshot(page, round_id):
    """
    Descarga todos los jugadores con mvp > 0 para una ronda dada.
    Retorna dict: fm_player_id → mvp_count_acumulado
    """
    snapshot = {}
    limit    = 100
    url      = f"{API_BASE}/players/statistics/all?round_id={round_id}&limit={limit}&offset=0&sort_stat=mvp&sort_order=desc"
    data     = nav_json(page, url)
    if not data or "players" not in data:
        return snapshot

    # Solo nos interesan jugadores con mvp > 0; en cuanto aparezca mvp=0 podemos parar
    total_pages = data.get("totalPages", 1)
    players = data.get("players", [])
    for p in players:
        if (p.get("mvp") or 0) > 0:
            snapshot[p["id"]] = p["mvp"]

    # La lista viene ordenada desc por mvp; si la primera página ya tiene mvp=0 paramos
    if not snapshot:
        return snapshot

    # Paginar mientras sigan apareciendo mvp > 0
    offset = limit
    page_n = 2
    while offset < total_pages * limit:
        url  = f"{API_BASE}/players/statistics/all?round_id={round_id}&limit={limit}&offset={offset}&sort_stat=mvp&sort_order=desc"
        data = nav_json(page, url)
        if not data or "players" not in data:
            break
        batch = data.get("players", [])
        has_more = False
        for p in batch:
            if (p.get("mvp") or 0) > 0:
                snapshot[p["id"]] = p["mvp"]
                has_more = True
        if not has_more:
            break   # resto tiene mvp=0, ya terminamos
        offset += limit
        page_n += 1
        time.sleep(0.2)

    return snapshot


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    import urllib.request
    try:
        urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
    except Exception:
        sys.exit("Chrome no está corriendo con --remote-debugging-port=9222")

    print("=" * 60)
    print("Fantasy Manager AR — BPR por fecha (delta method)")
    print("=" * 60)

    fm_id_to_name = {}
    if FM_PATH.exists():
        with open(FM_PATH, encoding="utf-8") as f:
            for p in json.load(f):
                fm_id_to_name[p["id"]] = p.get("full_name", p.get("name", ""))

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx  = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # 1. Rondas cerradas, ordenadas cronológicamente
        print("\nObteniendo fechas cerradas...")
        rd = nav_json(page, f"{API_BASE}/rounds/ended/all")
        rounds = rd if isinstance(rd, list) else (
            rd.get("rounds") or rd.get("data") or
            next((v for v in rd.values() if isinstance(v, list)), [])
        ) if isinstance(rd, dict) else []

        # Ordenar por starting_at (las más viejas primero)
        rounds.sort(key=lambda r: r.get("starting_at", ""))
        print(f"  {len(rounds)} fechas: {[r.get('name', r.get('id')) for r in rounds]}")

        # 2. Snapshot de mvp acumulado por ronda
        snapshots = {}   # round_id → {player_id: mvp_acum}
        print()
        for rnd in rounds:
            rnd_id   = rnd["id"]
            rnd_name = rnd.get("name", rnd_id)
            print(f"  Fecha {rnd_name} (id={rnd_id}) ...", end=" ", flush=True)
            snap = fetch_mvp_snapshot(page, rnd_id)
            snapshots[rnd_id] = snap
            print(f"{len(snap)} jugadores con mvp>0")
            time.sleep(0.3)

        page.close()

    # 3. Delta entre rondas → detectar quién ganó BPR en cada fecha
    print("\nCalculando deltas BPR entre fechas...")
    bpr_events = []   # lista de {round_id, round_name, player_id, position_estimate, pts}

    round_ids = [r["id"] for r in rounds]
    round_names = {r["id"]: r.get("name", str(r["id"])) for r in rounds}

    for i, rnd_id in enumerate(round_ids):
        prev_snap = snapshots[round_ids[i-1]] if i > 0 else {}
        curr_snap = snapshots[rnd_id]

        # Jugadores con mvp que subió respecto a la ronda anterior
        gainers = []
        for pid, curr_mvp in curr_snap.items():
            prev_mvp = prev_snap.get(pid, 0)
            gained   = curr_mvp - prev_mvp
            if gained > 0:
                gainers.append((pid, gained))

        # Para la ronda 1 (sin previa): los que tienen mvp > 0 ganaron BPR
        # Ordenar por mvp total DESC como proxy de posición (mayor mvp = probablemente BPR1)
        gainers.sort(key=lambda x: curr_snap.get(x[0], 0), reverse=True)

        # Asignar posiciones 1, 2, 3
        pos = 1
        for pid, gained in gainers[:3]:
            pts = BPR_PTS.get(pos, 0)
            bpr_events.append({
                "round_id":   rnd_id,
                "round_name": round_names[rnd_id],
                "player_id":  pid,
                "position":   pos,
                "pts":        pts,
                "name":       fm_id_to_name.get(pid, str(pid)),
            })
            print(f"  Fecha {round_names[rnd_id]}: pos{pos} → {fm_id_to_name.get(pid, pid)} (+{gained} mvp) → {pts}pts")
            pos += 1
            if pos > 3:
                break

    # 4. Agregar por jugador
    bpr_by_player = {}
    for ev in bpr_events:
        pid = ev["player_id"]
        if pid not in bpr_by_player:
            bpr_by_player[pid] = {"bpr1": 0, "bpr2": 0, "bpr3": 0,
                                  "total_pts": 0, "appearances": 0,
                                  "name": ev["name"]}
        bpr_by_player[pid][f"bpr{ev['position']}"] += 1
        bpr_by_player[pid]["total_pts"]  += ev["pts"]
        bpr_by_player[pid]["appearances"] += 1

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bpr_by_player, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado en {OUT_PATH} — {len(bpr_by_player)} jugadores con BPR")
    print(f"Total fechas procesadas: {len(rounds)}")
    print(f"Total eventos BPR: {len(bpr_events)}")

    top = sorted(bpr_by_player.items(), key=lambda x: x[1]["total_pts"], reverse=True)[:15]
    print("\nTop 15 jugadores por puntos BPR acumulados:")
    print(f"  {'Nombre':<28} {'BPR1':>5} {'BPR2':>5} {'BPR3':>5} {'Pts':>6}")
    for pid, d in top:
        print(f"  {d['name']:<28} {d['bpr1']:>5} {d['bpr2']:>5} {d['bpr3']:>5} {d['total_pts']:>6}")


if __name__ == "__main__":
    main()
