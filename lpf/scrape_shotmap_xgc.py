#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_shotmap_xgc.py — xG real por gol concedido, usando shotmap por partido.

Para cada partido terminado de la LPF Apertura 2026:
  - Descarga /event/{id}/shotmap
  - Filtra shots con shotType="goal" y situation != "penalty"
  - Acumula xG por equipo defensor

Outputs:
  lpf/shotmap_xgc.json — por equipo:
    avg_xg_conceded   → xG promedio por gol concedido (excluyendo penales)
    pct_low_xg        → % de goles con xG < 0.12 (goles de lejos / golazos)
    pct_high_xg       → % de goles con xG > 0.30 (goles fáciles, área chica)
    box_vuln          → normalizado vs liga: positivo = más vulnerable adentro del área
    wide_vuln         → normalizado vs liga: positivo = más vulnerable a tiros de lejos
    goals_sample      → cantidad de goles en la muestra
"""

import json, sys, io, time, math
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_BASE      = "https://api.sofascore.com/api/v1"
TOURNAMENT_ID = 155
SEASON_ID     = 87913
TOTAL_ROUNDS  = 18  # ajustar si hay más fechas jugadas
CDP_URL       = "http://127.0.0.1:9222"

OUT_PATH = Path(__file__).parent / "shotmap_xgc.json"

# Club IDs de team_xgc.json
CLUB_IDS = {
    "Argentinos Juniors":              3216,
    "Boca Juniors":                    3202,
    "CA Independiente":                3209,
    "CA Lanús":                        3218,
    "CA Talleres":                     3210,
    "Club Atlético Belgrano":          3203,
    "Club Atlético Unión de Santa Fe": 3204,
    "Estudiantes de La Plata":         3206,
    "Gimnasia y Esgrima":              3205,
    "Huracán":                         7629,
    "Independiente Rivadavia":         36842,
    "Racing Club":                     3215,
    "River Plate":                     3211,
    "Rosario Central":                 3217,
    "San Lorenzo":                     3201,
    "Vélez Sarsfield":                 3208,
}
ID_TO_CLUB = {v: k for k, v in CLUB_IDS.items()}


def loc_xg(coords):
    """
    Estimate xG from SofaScore playerCoordinates.
    x=0 → goal line (attacking end), y=50 → center of pitch.
    Scale: 0–100 maps to ~105m (length) and ~68m (width).
    """
    x = coords.get("x", 50)
    y = coords.get("y", 50)
    dist_m   = (x / 100) * 105                    # meters from goal line
    lat_m    = abs((y - 50) / 100) * 68           # lateral offset from center
    dist     = math.sqrt(dist_m ** 2 + lat_m ** 2)
    # Goal half-width 3.66m; angle to goal in degrees
    angle    = math.degrees(math.atan2(7.32, max(dist_m, 0.5)))
    # Calibrated to typical open-play xG: ~0.40 at 10m central, ~0.06 at 25m
    xg       = 0.95 * math.exp(-0.115 * dist) * (angle / 55)
    return round(max(0.02, min(0.85, xg)), 3)


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(400)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(2 + attempt * 2)
    return None


def get_round_events(page, round_num):
    """Retorna lista de eventos (partidos) para una fecha dada."""
    url  = f"{API_BASE}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/round/{round_num}"
    data = nav_json(page, url)
    if not data:
        return []
    return data.get("events", [])


def get_shotmap(page, event_id):
    """Retorna lista de shots del partido."""
    url  = f"{API_BASE}/event/{event_id}/shotmap"
    data = nav_json(page, url)
    if not data:
        return []
    return data.get("shotmap", [])


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright && playwright install chromium")

    import urllib.request
    try:
        urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
        use_cdp = True
        print("Usando Chrome CDP en puerto 9222.")
    except Exception:
        use_cdp = False
        print("Chrome CDP no disponible — lanzando headless.")

    # xG por gol concedido, por equipo: club_id → [xg, xg, ...]
    goals_by_team = {cid: [] for cid in CLUB_IDS.values()}
    matches_seen  = set()

    with sync_playwright() as pw:
        if use_cdp:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
            ctx  = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
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
            ctx.new_page().goto("https://www.sofascore.com",
                                wait_until="domcontentloaded", timeout=30000)

        page = ctx.new_page()

        print(f"\nEscaneando {TOTAL_ROUNDS} fechas...")
        all_events = []

        for rnd in range(1, TOTAL_ROUNDS + 1):
            events = get_round_events(page, rnd)
            finished = [e for e in events
                        if e.get("status", {}).get("type") == "finished"
                        and e.get("id") not in matches_seen]
            for e in finished:
                matches_seen.add(e["id"])
            all_events.extend(finished)
            print(f"  Fecha {rnd:>2}: {len(finished)} partidos terminados")
            time.sleep(0.3)

        print(f"\nTotal partidos a procesar: {len(all_events)}")
        print("Descargando shotmaps...\n")

        for i, event in enumerate(all_events):
            eid      = event["id"]
            home_id  = event.get("homeTeam", {}).get("id")
            away_id  = event.get("awayTeam", {}).get("id")
            home_nm  = event.get("homeTeam", {}).get("name", "?")
            away_nm  = event.get("awayTeam", {}).get("name", "?")

            shots = get_shotmap(page, eid)

            goals = [s for s in shots
                     if s.get("shotType") == "goal"
                     and s.get("situation") != "penalty"]

            for s in goals:
                xg      = loc_xg(s.get("playerCoordinates") or {})
                is_home = s.get("isHome", False)
                # El gol lo hizo el atacante; el defensor es el equipo contrario
                def_id  = away_id if is_home else home_id
                if def_id in goals_by_team:
                    goals_by_team[def_id].append(xg)

            goal_count = len(goals)
            print(f"  [{i+1:>3}/{len(all_events)}] {home_nm} vs {away_nm} — {goal_count} goles (non-pen)")
            time.sleep(0.25)

        page.close()

    # ── Calcular métricas por equipo ──
    print("\n" + "=" * 70)
    print(f"{'Equipo':<36} {'N':>4} {'avgXG':>6} {'pct<.12':>8} {'pct>.30':>8}")
    print("=" * 70)

    # Liga avg para normalizar
    all_xg = [xg for lst in goals_by_team.values() for xg in lst]
    league_avg_xg   = sum(all_xg) / len(all_xg) if all_xg else 0.18
    league_pct_low  = sum(1 for x in all_xg if x < 0.12) / len(all_xg) if all_xg else 0.20
    league_pct_high = sum(1 for x in all_xg if x > 0.30) / len(all_xg) if all_xg else 0.35

    # Bayesian prior strength: equivale a creer que los primeros K goles son de liga promedio
    K_SHRINK = 10

    result = {}
    for club, cid in CLUB_IDS.items():
        lst  = goals_by_team[cid]
        n    = len(lst)
        if n == 0:
            avg_xg   = league_avg_xg
            pct_low  = league_pct_low
            pct_high = league_pct_high
        else:
            avg_xg   = sum(lst) / n
            pct_low  = sum(1 for x in lst if x < 0.12) / n
            pct_high = sum(1 for x in lst if x > 0.30) / n

        # Shrinkage toward league mean — reduce el ruido para muestras chicas (N < ~15)
        w = n / (n + K_SHRINK)
        shrunk_avg_xg  = w * avg_xg  + (1 - w) * league_avg_xg
        shrunk_pct_low = w * pct_low + (1 - w) * league_pct_low

        # box_vuln: avg_xg shrunk vs liga → más alto = más goles fáciles (área chica)
        # wide_vuln: pct_low shrunk vs liga → más alto = más % goles de lejos
        box_vuln  = round(shrunk_avg_xg  - league_avg_xg,  3)
        wide_vuln = round(shrunk_pct_low - league_pct_low,  3)

        result[club] = {
            "club_id":          cid,
            "goals_sample":     n,
            "avg_xg_conceded":  round(avg_xg,       3),
            "avg_xg_shrunk":    round(shrunk_avg_xg, 3),
            "pct_low_xg":       round(pct_low,       3),
            "pct_low_shrunk":   round(shrunk_pct_low, 3),
            "pct_high_xg":      round(pct_high,      3),
            "box_vuln":         box_vuln,
            "wide_vuln":        wide_vuln,
            "league_avg_xg":    round(league_avg_xg,  3),
            "league_pct_low":   round(league_pct_low, 3),
        }
        shrink_flag = " *" if n < 12 else ""
        print(f"  {club:<36} {n:>4}  {avg_xg:>5.3f}→{shrunk_avg_xg:.3f}  "
              f"{pct_low*100:>5.1f}%→{shrunk_pct_low*100:.1f}%  "
              f"box={box_vuln:+.3f}  wide={wide_vuln:+.3f}{shrink_flag}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado en {OUT_PATH}")
    print(f"Liga avg xG/gol: {league_avg_xg:.3f}  |  Liga pct goles lejanos: {league_pct_low*100:.1f}%")

    # Top vulnerables
    print("\nMás vulnerables adentro del área (box_vuln alto = goles fáciles):")
    for club, d in sorted(result.items(), key=lambda x: x[1]["box_vuln"], reverse=True)[:5]:
        print(f"  {club:<36} box_vuln={d['box_vuln']:+.3f}  avg_xg={d['avg_xg_conceded']:.3f}")

    print("\nMás vulnerables a tiros lejanos (wide_vuln alto = más % de goles low-xG):")
    for club, d in sorted(result.items(), key=lambda x: x[1]["wide_vuln"], reverse=True)[:5]:
        print(f"  {club:<36} wide_vuln={d['wide_vuln']:+.3f}  pct_low={d['pct_low_xg']*100:.1f}%")


if __name__ == "__main__":
    main()
