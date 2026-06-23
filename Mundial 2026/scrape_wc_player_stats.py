#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_player_stats.py — Stats de club 2024-25 + internacionales por jugador (Mundial 2026)

Estrategia:
  1. Últimos eventos del jugador → filtra no-selección → identifica torneo/temporada de club
  2. Tournament stats endpoint (/player/{id}/unique-tournament/{tid}/season/{sid}/statistics/overall)
  3. Los mismos eventos → filtra partidos de selección → agrega stats internacionales

Selecciones con >SQUAD_THRESHOLD jugadores en SofaScore se omiten (squad no confirmado).
Para incluirlas igual: python scrape_wc_player_stats.py --all

Uso:
    python "Mundial 2026/scrape_wc_player_stats.py"
    python "Mundial 2026/scrape_wc_player_stats.py" --resume
    python "Mundial 2026/scrape_wc_player_stats.py" --all
    python "Mundial 2026/scrape_wc_player_stats.py" --test 5
"""

import json, time, random, sys, io, argparse
from pathlib import Path
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SQUADS_PATH = Path(__file__).parent / "wc2026_squads.json"
OUT_PATH    = Path(__file__).parent / "wc2026_player_stats.json"
BASE        = "https://api.sofascore.com/api/v1"

# Umbral de jugadores: squads con más de esto se consideran "no confirmados"
SQUAD_THRESHOLD = 26

# Temporada 2024-25: solo aceptamos seasons que cubran este rango
SEASON_START_YEAR = 2024
SEASON_END_YEAR   = 2025

# Mínimo de minutos en club para que los stats sean confiables
MIN_CLUB_MINS = 200

# Últimos N eventos internacionales a considerar para stats intl
MAX_INTL_EVENTS = 20


_XCAPTCHA   = ""
_XREQUESTED = "441959"


def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            cap = _XCAPTCHA.replace("'", "\\'")
            xrq = _XREQUESTED
            result = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        credentials: 'include',
                        headers: {{
                            'x-captcha': '{cap}',
                            'x-requested-with': '{xrq}',
                            'Accept': 'application/json'
                        }}
                    }});
                    return await r.text();
                }} catch(e) {{ return JSON.stringify({{fetch_error: e.toString()}}); }}
            }}""")
            if not result:
                time.sleep(2)
                continue
            data = json.loads(result)
            if ("error" in data or "fetch_error" in data) and "events" not in data and "statistics" not in data:
                time.sleep(2 + attempt * 2)
                continue
            return data
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def get_club_stats(page, player_id, national_team_id):
    """
    Busca stats de club via el torneo/temporada inferidos desde los últimos eventos.
    Estrategia: get events → filtra no-selección → identifica torneo más frecuente → stats.
    Devuelve (stats_dict, tournament_id, season_id, team_name) o (None, None, None, None).
    """
    from collections import Counter

    # Obtener últimos eventos (pueden ser de club y selección mezclados)
    data = nav_json(page, f"{BASE}/player/{player_id}/events/last/0")
    events = (data or {}).get("events", [])

    # Filtrar eventos de club (excluir los de la selección)
    club_events = [
        e for e in events
        if e.get("homeTeam", {}).get("id") != national_team_id
        and e.get("awayTeam", {}).get("id") != national_team_id
    ]

    if not club_events:
        return None, None, None, None

    # Identificar el torneo/temporada más frecuente (la liga principal)
    tour_counter = Counter()
    for e in club_events:
        ut   = e.get("tournament", {}).get("uniqueTournament", {})
        s    = e.get("season", {})
        ut_id = ut.get("id")
        s_id  = s.get("id")
        t_name = ut.get("name", "")
        # Extraer nombre del equipo del jugador en este partido
        if ut_id and s_id:
            tour_counter[(ut_id, s_id, t_name)] += 1

    if not tour_counter:
        return None, None, None, None

    (ut_id, s_id, t_name), _ = tour_counter.most_common(1)[0]

    # Inferir equipo del jugador: el team_id que aparece más en sus eventos = el suyo
    team_id_freq = Counter()
    team_id_name = {}
    for e in club_events:
        if (e.get("tournament", {}).get("uniqueTournament", {}).get("id") == ut_id
                and e.get("season", {}).get("id") == s_id):
            for side in ("homeTeam", "awayTeam"):
                tid  = e.get(side, {}).get("id")
                tnam = e.get(side, {}).get("name", "")
                if tid:
                    team_id_freq[tid] += 1
                    team_id_name[tid]  = tnam
    player_team_id = team_id_freq.most_common(1)[0][0] if team_id_freq else None
    team = team_id_name.get(player_team_id, "")

    # Stats detalladas con xG/xA
    url   = f"{BASE}/player/{player_id}/unique-tournament/{ut_id}/season/{s_id}/statistics/overall"
    sdata = nav_json(page, url)
    if not sdata or "statistics" not in sdata:
        return None, ut_id, s_id, team

    stats = sdata["statistics"]
    stats["_tournament"] = t_name
    stats["_team"]       = team
    return stats, ut_id, s_id, team


def get_intl_stats(page, player_id, national_team_id):
    """
    Obtiene stats internacionales del jugador filtrando eventos con su selección.
    Devuelve dict con stats agregadas o None.
    """
    # Obtener últimos 40 eventos (2 páginas)
    all_events = []
    for pg in range(3):
        data = nav_json(page, f"{BASE}/player/{player_id}/events/last/{pg}")
        if not data or not data.get("events"):
            break
        all_events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.3)

    # Filtrar eventos de la selección
    intl_events = []
    for e in all_events:
        h_id = e.get("homeTeam", {}).get("id")
        a_id = e.get("awayTeam", {}).get("id")
        if h_id == national_team_id or a_id == national_team_id:
            intl_events.append(e)

    intl_events.sort(key=lambda x: x.get("startTimestamp", 0), reverse=True)
    intl_events = intl_events[:MAX_INTL_EVENTS]

    if not intl_events:
        return None

    # Acumular stats de cada partido
    agg = {
        "matchesPlayed": 0, "minutesPlayed": 0,
        "goals": 0, "assists": 0,
        "yellowCards": 0, "redCards": 0,
        "totalShots": 0, "keyPasses": 0,
        "expectedGoals": 0.0, "expectedAssists": 0.0,
        "goalsConceded": 0, "cleanSheets": 0, "saves": 0,
        "bigChancesCreated": 0,
    }
    has_xg = False

    for ev in intl_events:
        eid  = ev.get("id")
        sdata = nav_json(page, f"{BASE}/event/{eid}/player/{player_id}/statistics")
        if not sdata:
            time.sleep(0.3)
            continue
        st = sdata.get("statistics", {})
        mins = st.get("minutesPlayed") or 0
        if mins == 0:
            time.sleep(0.2)
            continue

        agg["matchesPlayed"]  += 1
        agg["minutesPlayed"]  += mins
        agg["goals"]          += st.get("goals") or 0
        agg["assists"]        += st.get("goalAssist") or 0
        agg["yellowCards"]    += st.get("yellowCards") or 0
        agg["redCards"]       += st.get("redCards") or 0
        agg["totalShots"]     += st.get("totalShots") or 0
        agg["keyPasses"]      += st.get("keyPass") or 0
        agg["goalsConceded"]  += st.get("goalsConceded") or 0
        agg["saves"]          += st.get("saves") or 0
        if st.get("cleanSheet"):
            agg["cleanSheets"] += 1
        xg = st.get("expectedGoals")
        xa = st.get("expectedAssists")
        if xg is not None:
            agg["expectedGoals"]   += xg
            has_xg = True
        else:
            shots = st.get("totalShots") or 0
            agg["expectedGoals"]   += shots * 0.095
        if xa is not None:
            agg["expectedAssists"] += xa
        else:
            agg["expectedAssists"] += (st.get("keyPass") or 0) * 0.08
        agg["bigChancesCreated"]   += st.get("bigChanceCreated") or 0

        time.sleep(0.25 + random.random() * 0.2)

    agg["_has_real_xg"] = has_xg
    return agg if agg["matchesPlayed"] > 0 else None


def normalize_stats(raw, source="club"):
    """
    Normaliza stats crudas al formato común del modelo.
    Funciona con el output del career endpoint o del tournament stats endpoint.
    """
    mins   = raw.get("minutesPlayed") or raw.get("totalMinutesPlayed") or 0
    games  = raw.get("matchesPlayed") or raw.get("appearances") or 0
    goals  = raw.get("goals") or 0
    asists = raw.get("assists") or raw.get("goalAssist") or 0
    yel    = raw.get("yellowCards") or 0
    red    = raw.get("redCards") or 0
    shots  = raw.get("totalShots") or 0
    kp     = raw.get("keyPasses") or raw.get("keyPass") or 0
    gc_big = raw.get("bigChancesCreated") or 0

    xg_raw = raw.get("expectedGoals") or raw.get("xg")
    xa_raw = raw.get("expectedAssists") or raw.get("xa")
    xg = float(xg_raw) if xg_raw is not None else shots * 0.095
    xa = float(xa_raw) if xa_raw is not None else kp * 0.08

    # GK
    gc      = raw.get("goalsConceded") or 0
    vi      = raw.get("cleanSheets") or raw.get("cleanSheet") or 0
    saves   = raw.get("saves") or raw.get("saves") or 0
    saves_in  = raw.get("savesInsideBox") or raw.get("savesFromInsideBox") or 0
    saves_out = raw.get("savesOutsideBox") or raw.get("savesFromOutsideBox") or 0

    return {
        "Minutos Jugados":    mins,
        "Partidos Jugados":   games,
        "Goles":              goals,
        "Asistencias":        asists,
        "Amarillas":          yel,
        "Rojas":              red,
        "xG":                 round(xg, 4),
        "xA":                 round(xa, 4),
        "Remates Totales":    shots,
        "Pases Clave":        kp,
        "Grandes Chances Creadas": gc_big,
        "Goles Recibidos":    gc,
        "Vallas Invictas":    vi,
        "Atajadas":           saves,
        "Atajadas Dentro":    saves_in,
        "Atajadas Fuera":     saves_out,
        "_source":            source,
        "_has_real_xg":       (xg_raw is not None),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--all",    action="store_true", help="Incluir squads con >30 jugadores")
    parser.add_argument("--test",   type=int, default=0, help="Procesar solo N jugadores")
    args = parser.parse_args()

    with open(SQUADS_PATH, encoding="utf-8") as f:
        squads = json.load(f)

    # Filtrar squads por tamaño
    skipped_teams = []
    players_to_scrape = []
    for team_name, team_data in squads.items():
        n = len(team_data["players"])
        if not args.all and n > SQUAD_THRESHOLD:
            skipped_teams.append(f"{team_name} ({n})")
            continue
        national_team_id = team_data["team_id"]
        group            = team_data["group"]
        for p in team_data["players"]:
            if not p.get("id"):
                continue
            players_to_scrape.append({
                "player_id":        p["id"],
                "name":             p.get("name") or p.get("shortName", "?"),
                "position":         p.get("position", "M"),
                "national_team_id": national_team_id,
                "national_team":    team_name,
                "group":            group,
                "jersey":           p.get("jerseyNumber"),
            })

    if skipped_teams:
        print(f"Squads omitidos (>{SQUAD_THRESHOLD} jugadores): {', '.join(skipped_teams)}")
        print("  → Corré con --all para incluirlos\n")

    if args.test:
        players_to_scrape = players_to_scrape[:args.test]

    # Cargar progreso anterior si --resume
    result = {}
    if OUT_PATH.exists() and args.resume:
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} jugadores ya procesados.\n")

    total = len(players_to_scrape)
    print(f"Jugadores a procesar: {total}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with sync_playwright() as pw:
        # Conectar a Chrome real via CDP (mismo enfoque que form_v4)
        browser = pw.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
        ctx = browser.contexts[0]

        # Capturar x-captcha desde páginas SofaScore ya abiertas
        sofa_pages = [p for p in ctx.pages if "sofascore.com/football/player" in p.url]
        if not sofa_pages:
            sofa_pages = [p for p in ctx.pages if "sofascore.com" in p.url]
        page = sofa_pages[0] if sofa_pages else ctx.new_page()

        captured = {}
        def on_req(request):
            if "sofascore.com/api/v1/player" in request.url and "events/last" in request.url:
                h = dict(request.headers)
                if h.get("x-captcha"):
                    captured.update(h)
        page.on("request", on_req)
        if not sofa_pages or "player" not in page.url:
            page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
        else:
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, 100)")
            page.wait_for_timeout(2000)
        page.remove_listener("request", on_req)
        if not captured.get("x-captcha"):
            page.on("request", on_req)
            page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            page.remove_listener("request", on_req)

        global _XCAPTCHA, _XREQUESTED
        _XCAPTCHA   = captured.get("x-captcha", "")
        _XREQUESTED = captured.get("x-requested-with", "441959")
        print(f"Chrome CDP | token={'OK' if _XCAPTCHA else 'MISSING'} | xrw={_XREQUESTED}")

        # Verificar API
        test = nav_json(page, f"{BASE}/player/839956/events/last/0")
        if not test or "error" in test:
            print("ERROR: API no responde")
            return
        print("API OK\n")

        for i, p in enumerate(players_to_scrape, 1):
            pid_str = str(p["player_id"])
            if pid_str in result and args.resume:
                continue

            print(f"[{i}/{total}] {p['name']} ({p['national_team']} | {p['position']})")

            # ── Club stats (temporada de club más reciente) ─────────────────
            club_raw, t_id, s_id, club_team = get_club_stats(page, p["player_id"], p["national_team_id"])
            time.sleep(0.4)

            if club_raw:
                club_stats = normalize_stats(club_raw, source="club")
                mins_ok = club_stats["Minutos Jugados"] >= MIN_CLUB_MINS
                xg_flag  = club_raw.get("_has_real_xg", False)
                print(f"    Club: {club_team} | {club_stats['Minutos Jugados']}min "
                      f"{club_stats['Goles']}G {club_stats['Asistencias']}A "
                      f"xG={club_stats['xG']:.2f} xA={club_stats['xA']:.2f}"
                      f"{'  [real xG]' if xg_flag else '  [proxy]'}")
            else:
                club_stats = None
                print(f"    Club: sin datos de temporada vigente")

            # ── Intl stats ──────────────────────────────────────────────────
            intl_raw = get_intl_stats(page, p["player_id"], p["national_team_id"])

            if intl_raw:
                intl_stats = normalize_stats(intl_raw, source="intl")
                print(f"    Intl: {intl_stats['Partidos Jugados']}PJ {intl_stats['Minutos Jugados']}min "
                      f"{intl_stats['Goles']}G {intl_stats['Asistencias']}A "
                      f"xG={intl_stats['xG']:.2f} xA={intl_stats['xA']:.2f}")
            else:
                intl_stats = None
                print(f"    Intl: sin partidos con la selección")

            result[pid_str] = {
                "name":             p["name"],
                "position":         p["position"],
                "national_team":    p["national_team"],
                "national_team_id": p["national_team_id"],
                "group":            p["group"],
                "jersey":           p["jersey"],
                "club_team":        club_team or "",
                "club_tournament":  t_id,
                "club_season":      s_id,
                "club_stats":       club_stats,
                "intl_stats":       intl_stats,
            }

            # Guardar progresivamente
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            time.sleep(1.0 + random.random() * 0.8)

        browser.close()

    print(f"\nListo. {len(result)} jugadores en {OUT_PATH}")

    # Resumen
    with_club  = sum(1 for v in result.values() if v.get("club_stats"))
    with_intl  = sum(1 for v in result.values() if v.get("intl_stats"))
    with_real_xg = sum(1 for v in result.values()
                       if (v.get("club_stats") or {}).get("_has_real_xg"))
    print(f"  Con stats de club:   {with_club}/{len(result)}")
    print(f"  Con stats intl:      {with_intl}/{len(result)}")
    print(f"  Con xG real (club):  {with_real_xg}/{len(result)}")


if __name__ == "__main__":
    main()
