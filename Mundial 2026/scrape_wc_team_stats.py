#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_team_stats.py — Stats defensivos por selección (xGC, vallas invictas, etc.)

Usa los últimos partidos de cada selección (clasificatorias + amistosos recientes)
para calcular xGC/pg, gc_pg, vi_rate y def_score — insumo del FDR en el modelo.

Uso:
    python "Mundial 2026/scrape_wc_team_stats.py"
"""

import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SQUADS_PATH = Path(__file__).parent / "wc2026_squads.json"
OUT_PATH    = Path(__file__).parent / "wc2026_team_stats.json"
BASE        = "https://api.sofascore.com/api/v1"

SQUAD_THRESHOLD = 30
MIN_EVENTS      = 5
MAX_EVENTS      = 20

# Ranking FIFA actual (mayo 2026) — corrector de calidad sobre resultados recientes
# Escala 0-100: top1=100, top10≈82, top20≈65, top30≈50, top50≈30
FIFA_RANKINGS = {
    "Argentina": 100, "France": 95,  "Spain": 92,    "England": 88,
    "Brazil": 85,     "Portugal": 82, "Netherlands": 79, "Belgium": 76,
    "Germany": 74,    "Uruguay": 71,  "Colombia": 68, "Morocco": 65,
    "USA": 62,        "Croatia": 60,  "Switzerland": 58, "Japan": 56,
    "Senegal": 54,    "Mexico": 52,   "South Korea": 50, "Australia": 47,
    "Austria": 45,    "Denmark": 43,  "Norway": 41,   "Czechia": 39,
    "Turkey": 38,     "Ecuador": 37,  "Iran": 36,     "Canada": 35,
    "Algeria": 34,    "Scotland": 33, "Egypt": 32,    "Tunisia": 31,
    "Sweden": 30,     "Saudi Arabia": 28, "Ghana": 27, "South Africa": 25,
    "Panama": 24,     "Paraguay": 23, "Ivory Coast": 22, "Bolivia": 20,
    "Cabo Verde": 35, "Côte d'Ivoire": 45, "Cote d'Ivoire": 45,
    "Curaçao": 18,    "New Zealand": 20, "DR Congo": 30, "Haiti": 17,
    "Jordan": 28,     "Iraq": 26,     "Bosnia & Herzegovina": 35,
    "Qatar": 25,      "Uzbekistan": 32, "Colombia": 68,
}

def fifa_rank_score(team_name):
    """Devuelve 0-100 según ranking FIFA (proxy de calidad histórica)."""
    # Intentar variantes del nombre
    for name in [team_name, team_name.replace("é","e"), team_name.replace("ô","o")]:
        if name in FIFA_RANKINGS:
            return FIFA_RANKINGS[name]
    return 40  # default: equipo de nivel medio


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


FRIENDLY_TOURNAMENT_IDS = {313, 1108, 9596}  # International friendlies en SofaScore

def get_team_events(page, team_id):
    """Devuelve hasta MAX_EVENTS últimos partidos competitivos del equipo."""
    events = []
    for pg in range(4):
        data = nav_json(page, f"{BASE}/team/{team_id}/events/last/{pg}")
        if not data or not data.get("events"):
            break
        events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.35)
    # Filtrar amistosos — solo partidos competitivos tienen shotmap con datos útiles
    competitive = []
    for e in events:
        ut_id = (e.get("tournament", {}).get("uniqueTournament") or {}).get("id", 0)
        if ut_id not in FRIENDLY_TOURNAMENT_IDS:
            competitive.append(e)
    competitive.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
    return competitive[:MAX_EVENTS]


def get_defensive_profile(page, events, team_id):
    """
    Calcula vulnerabilidad defensiva por zona usando shotmap de los últimos partidos.
    Retorna dict con box_vuln, wide_vuln, aerial_vuln (rango -1..1 vs liga media).

    Lógica (misma que LPF scrape_shotmap_xgc.py):
      - xG alto (>0.15) → remate de área → box_vuln
      - xG bajo  (<0.08) → remate lejano/wide → wide_vuln
      - header   (bodyPart=head) → aerial_vuln
    """
    finished = [e for e in events if (e.get("status") or {}).get("type") == "finished"]
    # Limitar a 10 partidos para no sobrecargar la API
    sample = finished[:10]

    all_shots_against = []

    for ev in sample:
        eid    = ev.get("id")
        is_home = ev.get("homeTeam", {}).get("id") == team_id
        data   = nav_json(page, f"{BASE}/event/{eid}/shotmap")
        if not data:
            time.sleep(0.3)
            continue
        shots = data.get("shotmap") or data.get("shots") or []
        for s in shots:
            # isHome=True → shot pertenece al home team
            # Shots "against" este equipo = shots del rival
            shot_is_home = s.get("isHome")
            if shot_is_home is None:
                continue  # sin campo isHome, no podemos saber de quién es
            if is_home and shot_is_home:
                continue   # equipo es home → saltear shots propios (isHome=True)
            if not is_home and not shot_is_home:
                continue   # equipo es away → saltear shots propios (isHome=False)
            if s.get("shotType") in ("penalty", "ownGoal"):
                continue
            # xG: usar valor de la API si existe; sino, proxy desde coordenadas
            xg = s.get("xg") or s.get("expectedGoal")
            if not xg:
                coords = s.get("playerCoordinates") or {}
                x = coords.get("x", 50)
                y = coords.get("y", 50)
                # Coordenadas en perspectiva del equipo LOCAL (x=0=arco local, x=100=arco visitante)
                # Tiros contra el LOCAL (isHome=False) atacan hacia x=0 → peligro crece al bajar x
                # Tiros contra el VISITANTE (isHome=True) atacan hacia x=100 → peligro crece al subir x
                dist_to_goal = x if is_home else (100 - x)
                dy = abs(y - 50)
                dist2 = dist_to_goal**2 + dy**2
                xg = max(0.02, min(0.85, 3.5 / (1 + dist2 / 80)))
            body_part = (s.get("bodyPart") or "").lower()
            all_shots_against.append({"xg": float(xg), "head": "head" in body_part})
        time.sleep(0.25)

    if not all_shots_against:
        return None

    n          = len(all_shots_against)
    avg_xg     = sum(s["xg"] for s in all_shots_against) / n
    pct_high   = sum(1 for s in all_shots_against if s["xg"] > 0.15) / n  # box
    pct_low    = sum(1 for s in all_shots_against if s["xg"] < 0.08) / n  # wide/long
    pct_head   = sum(1 for s in all_shots_against if s["head"]) / n

    return {
        "avg_xg_against": round(avg_xg, 4),
        "pct_high_xg":    round(pct_high, 3),
        "pct_low_xg":     round(pct_low, 3),
        "pct_aerial":     round(pct_head, 3),
        "n_shots":        n,
    }


def compute_team_stats(events, team_id):
    """
    Calcula stats defensivas/ofensivas de la selección a partir de sus últimos partidos.
    Solo usa partidos que tienen score (finalizados).
    """
    gc_list, gf_list, vi_list = [], [], []

    for e in events:
        status = (e.get("status") or {}).get("type", "")
        if status not in ("finished",):
            continue

        h_id     = e.get("homeTeam", {}).get("id")
        score_h  = e.get("homeScore", {}).get("current")
        score_a  = e.get("awayScore", {}).get("current")
        if score_h is None or score_a is None:
            continue

        is_home = (h_id == team_id)
        my_gf   = score_h if is_home else score_a
        my_gc   = score_a if is_home else score_h

        gc_list.append(my_gc)
        gf_list.append(my_gf)
        vi_list.append(1 if my_gc == 0 else 0)

    n = len(gc_list)
    if n < MIN_EVENTS:
        return None

    gc_pg   = sum(gc_list) / n
    gf_pg   = sum(gf_list) / n
    vi_rate = sum(vi_list) / n
    xgc_pg  = gc_pg   # proxy; se refina con shotmap si está disponible

    # def_score 0-100 basado en resultados recientes
    gc_norm   = max(0.0, min(100.0, 100 - (xgc_pg - 0.4) * 52))
    vi_norm   = min(100.0, vi_rate * 130)
    def_recent = gc_norm * 0.65 + vi_norm * 0.35

    return {
        "matches":    n,
        "gc_pg":      round(gc_pg,   3),
        "gf_pg":      round(gf_pg,   3),
        "xgc_pg":     round(xgc_pg,  3),
        "vi_pct":     round(vi_rate * 100, 1),
        "def_recent": round(def_recent, 1),
        "att_score":  round(min(100.0, gf_pg * 33), 1),
    }


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with open(SQUADS_PATH, encoding="utf-8") as f:
        squads = json.load(f)

    teams = [
        (name, data["team_id"], data["group"])
        for name, data in squads.items()
        if len(data["players"]) <= SQUAD_THRESHOLD
    ]

    print(f"Selecciones a procesar: {len(teams)}")
    result = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-419", viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Paso 1: recopilar datos base + shotmap por equipo
        raw_results = {}
        for i, (team_name, team_id, group) in enumerate(teams, 1):
            print(f"  [{i}/{len(teams)}] [{group}] {team_name}...", end=" ", flush=True)
            events = get_team_events(page, team_id)
            stats  = compute_team_stats(events, team_id)
            if not stats:
                print(f"sin datos ({len(events)} eventos)")
                raw_results[team_name] = None
            else:
                # Shotmap defensivo
                profile = get_defensive_profile(page, events, team_id)
                print(f"OK  {stats['matches']}PJ  gc={stats['gc_pg']:.2f}  vi={stats['vi_pct']:.0f}%"
                      f"  shots={'OK' if profile else '—'}")
                raw_results[team_name] = {
                    "team_id": team_id, "group": group,
                    **stats, "shotmap": profile,
                }
            time.sleep(1.2)

        browser.close()

    # Paso 2: calcular perfiles de zona normalizados vs liga media
    profiles_data = {k: v["shotmap"] for k, v in raw_results.items()
                     if v and v.get("shotmap")}
    league_avg_xg  = (sum(p["avg_xg_against"] for p in profiles_data.values()) /
                      max(len(profiles_data), 1))
    league_pct_low = (sum(p["pct_low_xg"]     for p in profiles_data.values()) /
                      max(len(profiles_data), 1))
    league_pct_aer = (sum(p["pct_aerial"]      for p in profiles_data.values()) /
                      max(len(profiles_data), 1))

    for team_name, raw in raw_results.items():
        if not raw:
            result[team_name] = {
                "team_id": 0, "group": "?",
                "matches": 0, "gc_pg": 0.9, "gf_pg": 0.9,
                "xgc_pg": 0.9, "vi_pct": 25.0,
                "def_score": 50.0, "att_score": 50.0, "fdr": 3,
                "box_vuln": 0.0, "wide_vuln": 0.0, "aerial_vuln": 0.0,
            }
            continue

        # Perfiles de zona (mismo cálculo que LPF)
        sp = raw.get("shotmap")
        if sp:
            box_dev  = (sp["avg_xg_against"] - league_avg_xg)  / max(league_avg_xg,  0.01)
            wide_dev = (sp["pct_low_xg"]     - league_pct_low)  / max(league_pct_low, 0.01)
            aer_dev  = (sp["pct_aerial"]      - league_pct_aer)  / max(league_pct_aer, 0.01)
        else:
            box_dev = wide_dev = aer_dev = 0.0

        # def_score final: 75% resultados recientes + 25% ranking FIFA
        rank_score  = fifa_rank_score(team_name)
        # rank_score alto = equipo fuerte = mejor defensa esperada → def_score más alto
        rank_def    = rank_score   # ya en escala 0-100
        def_score   = round(0.75 * raw["def_recent"] + 0.25 * rank_def, 1)
        def_score   = max(0.0, min(100.0, def_score))

        fdr = (5 if def_score >= 72 else
               4 if def_score >= 56 else
               3 if def_score >= 38 else
               2 if def_score >= 20 else 1)

        result[team_name] = {
            "team_id":     raw["team_id"],
            "group":       raw["group"],
            "matches":     raw["matches"],
            "gc_pg":       raw["gc_pg"],
            "gf_pg":       raw["gf_pg"],
            "xgc_pg":      raw["xgc_pg"],
            "vi_pct":      raw["vi_pct"],
            "def_recent":  raw["def_recent"],
            "def_score":   def_score,
            "att_score":   raw["att_score"],
            "fdr":         fdr,
            "fifa_rank_score": rank_score,
            "box_vuln":    round(max(-1.0, min(1.0, box_dev)),  3),
            "wide_vuln":   round(max(-1.0, min(1.0, wide_dev)), 3),
            "aerial_vuln": round(max(-1.0, min(1.0, aer_dev)),  3),
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado: {OUT_PATH}")
    print("\nTabla FDR (1=difícil atacar, 5=fácil atacar):")
    sorted_teams = sorted(result.items(), key=lambda x: x[1]["def_score"], reverse=True)
    for name, d in sorted_teams:
        bv = f"box={d.get('box_vuln',0):+.2f}" if d.get("box_vuln") else ""
        print(f"  [{d['group']}] {name:<30} def={d['def_score']:>5}  fdr={d['fdr']}  "
              f"gc={d['gc_pg']:.2f}  fifa={d.get('fifa_rank_score',0)}  {bv}")


if __name__ == "__main__":
    main()
