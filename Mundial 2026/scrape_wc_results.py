#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_results.py — Resultados del Mundial 2026 con datos completos por jugador.

Por cada partido jugado extrae:
  - Lineups confirmados + minutos reales (desde incidents de sustitución)
  - Goals, tarjetas, sustituciones con minuto exacto
  - Stats por jugador: xG, xA, rating, goles, asistencias, tarjetas, minutos
  - Shotmap: perfil de ataque por zona (izq/centro/der) por equipo
  - Stats de equipo (posesión, remates, etc.)

Outputs:
  wc2026_wc_results.json  — datos por partido + perfiles acumulados de equipo
  wc2026_form.json        — WC matches agregados al form con weight=3
  wc2026_lineups.json     — bajas para siguiente fecha (roja directa / lesión)

Uso:
    python "Mundial 2026/scrape_wc_results.py"             # todos los partidos jugados
    python "Mundial 2026/scrape_wc_results.py" --fecha 1  # solo fecha 1
    python "Mundial 2026/scrape_wc_results.py" --force    # reprocesa aunque ya existan
"""

import json, time, random, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE              = "https://www.sofascore.com/api/v1"
FIXTURES_PATH     = Path(__file__).parent / "wc2026_fixtures.json"
FORM_PATH         = Path(__file__).parent / "wc2026_form.json"
LINEUPS_PATH      = Path(__file__).parent / "wc2026_lineups.json"
WC_RESULTS_PATH   = Path(__file__).parent / "wc2026_wc_results.json"
PLAYER_PATH       = Path(__file__).parent / "wc2026_player_stats.json"
SQUADS_PATH       = Path(__file__).parent / "wc2026_squads.json"

DECAY      = 0.82
WC_WEIGHT  = 3     # los partidos del Mundial pesan 3x en el cálculo de forma
N_FORM_MAX = 20    # máximo de matches guardados en el form (se usa el top N para compute)

_XREQUESTED = "441959"


# ── API helper ────────────────────────────────────────────────────────────────

def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            xrw = _XREQUESTED.replace("'", "\\'")
            result = page.evaluate(f"""(async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        credentials: 'include',
                        headers: {{
                            'x-requested-with': '{xrw}',
                            'Accept': 'application/json'
                        }}
                    }});
                    return await r.text();
                }} catch(e) {{ return JSON.stringify({{error: e.toString()}}); }}
            }})()""")
            if not result:
                time.sleep(2)
                continue
            data = json.loads(result)
            ok_keys = ("events", "statistics", "incidents", "shotmap", "lineups",
                       "player", "choices", "markets")
            if "error" in data and not any(k in data for k in ok_keys):
                time.sleep(2 + attempt * 2)
                continue
            return data
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


# ── Form computation ──────────────────────────────────────────────────────────

def form_stats(matches):
    """
    Computa form_xg_90 / form_xa_90 con decaimiento exponencial y weight por partido.
    WC matches tienen weight=3, el resto weight=1 (default).
    """
    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        if (m.get("mins") or 0) < 20:
            continue
        w = (DECAY ** i) * m.get("weight", 1.0)
        mins = m["mins"]
        w_xg    += (m.get("xg", 0) / mins * 90) * w
        w_xa    += (m.get("xa", 0) / mins * 90) * w
        total_w += w
    if total_w == 0:
        return None
    return {
        "form_xg_90": round(w_xg / total_w, 4),
        "form_xa_90": round(w_xa / total_w, 4),
        "n": len([m for m in matches if (m.get("mins") or 0) >= 20]),
    }


def add_to_form(form_data, pid_str, entry, player_name, team_name):
    """
    Inserta un partido WC al form del jugador y recomputa form_xg_90.
    No duplica si el event_id ya está.
    Retorna True si se agregó.
    """
    fd = form_data.setdefault(pid_str, {
        "name": player_name,
        "team": team_name,
        "matches": [],
    })
    existing_eids = {m.get("event_id") for m in fd.get("matches", [])}
    if entry["event_id"] in existing_eids:
        return False

    matches = [entry] + fd.get("matches", [])
    matches = matches[:N_FORM_MAX]
    fd["matches"] = matches

    new_form = form_stats(matches)
    if new_form:
        fd["form"] = new_form
    fd["v2"] = True
    return True


# ── Incidents parsing ─────────────────────────────────────────────────────────

def parse_incidents(inc_data, home_id, away_id):
    """
    Parsea incidents del partido:
      - Minuto final real (detectado por períodos FT/AET)
      - Sustituciones (para calcular minutos exactos)
      - Goles con tipo (abierto / pelota parada) y equipo
      - Tarjetas (amarillas, rojas)
      - Bajas para siguiente partido (roja directa o doble amarilla)
    """
    incidents = (inc_data or {}).get("incidents", [])

    final_min = 90
    for inc in incidents:
        if inc.get("incidentType") == "period" and inc.get("text") in ("FT", "AP", "AET"):
            t  = inc.get("time", 90)
            at = inc.get("addedTime") or 0
            final_min = max(final_min, t + at)

    subs_out  = {}   # player_id → minute_out
    subs_in   = {}   # player_id → minute_in
    player_side = {} # player_id → is_home

    for inc in incidents:
        if inc.get("incidentType") != "substitution":
            continue
        minute  = inc.get("time", 90)
        added   = inc.get("addedTime") or 0
        sub_min = minute + added * 0.5
        is_home = inc.get("isHome", True)
        pid_out = (inc.get("playerOut") or {}).get("id")
        pid_in  = (inc.get("playerIn")  or {}).get("id")
        if pid_out:
            subs_out[pid_out]    = min(subs_out.get(pid_out, sub_min), sub_min)
            player_side[pid_out] = is_home
        if pid_in:
            subs_in[pid_in]     = sub_min
            player_side[pid_in] = is_home

    goals = []
    for inc in incidents:
        if inc.get("incidentType") not in ("goal", "ownGoal"):
            continue
        if inc.get("rescinded"):
            continue
        minute    = inc.get("time", 0)
        added     = inc.get("addedTime") or 0
        inc_class = inc.get("incidentClass", "")
        is_home   = inc.get("isHome", True)
        player    = inc.get("player") or {}
        goals.append({
            "minute":     minute + added * 0.5,
            "player_id":  player.get("id"),
            "player_name": player.get("name", ""),
            "team_id":    home_id if is_home else away_id,
            "is_home":    is_home,
            "type":       "set_piece" if inc_class in ("fromSetPiece", "fromCorner", "penalty") else "open_play",
            "is_penalty": inc_class == "penalty",
            "is_own_goal": inc.get("incidentType") == "ownGoal",
        })

    cards        = []
    missing_next = []
    for inc in incidents:
        if inc.get("incidentType") != "card":
            continue
        player    = inc.get("player") or {}
        pid       = player.get("id")
        is_home   = inc.get("isHome", True)
        card_cls  = inc.get("incidentClass", "")  # "yellow", "yellowRed", "red"
        cards.append({
            "player_id":   pid,
            "player_name": player.get("name", ""),
            "team_id":     home_id if is_home else away_id,
            "is_home":     is_home,
            "type":        card_cls,
            "minute":      inc.get("time", 0),
        })
        if card_cls in ("red", "yellowRed"):
            missing_next.append({
                "player_id":   pid,
                "player_name": player.get("name", ""),
                "team_id":     home_id if is_home else away_id,
                "is_home":     is_home,
                "reason":      "suspension",
            })

    return {
        "subs_out":    subs_out,
        "subs_in":     subs_in,
        "player_side": player_side,
        "final_min":   final_min,
        "goals":       goals,
        "cards":       cards,
        "missing_next": missing_next,
    }


def compute_player_minutes(lu_data, inc, home_id, away_id):
    """
    Calcula minutos reales de cada jugador combinando lineups e incidents.
    Retorna: {player_id → {mins, status, is_home, team_id, name}}
    """
    final_min = inc["final_min"]
    result    = {}

    for side in ("home", "away"):
        is_home = side == "home"
        team_id = home_id if is_home else away_id
        sd      = (lu_data or {}).get(side) or {}

        for p in (sd.get("players") or []):
            player = p.get("player") or {}
            pid    = player.get("id")
            if not pid:
                continue
            end_min = inc["subs_out"].get(pid, final_min)
            result[pid] = {
                "mins":    max(1, round(end_min)),
                "status":  "starter",
                "is_home": is_home,
                "team_id": team_id,
                "name":    player.get("name") or player.get("shortName", ""),
            }

        for key in ("substitutes", "bench"):
            for p in (sd.get(key) or []):
                player = p.get("player") or {}
                pid    = player.get("id")
                if not pid:
                    continue
                if pid in inc["subs_in"]:
                    start = inc["subs_in"][pid]
                    result[pid] = {
                        "mins":    max(1, round(final_min - start)),
                        "status":  "sub_in",
                        "is_home": is_home,
                        "team_id": team_id,
                        "name":    player.get("name") or player.get("shortName", ""),
                    }

        for p in (sd.get("missingPlayers") or []):
            player = p.get("player") or {}
            pid    = player.get("id")
            if pid and pid not in result:
                result[pid] = {
                    "mins":    0,
                    "status":  "missing",
                    "is_home": is_home,
                    "team_id": team_id,
                    "name":    player.get("name") or player.get("shortName", ""),
                    "reason":  p.get("type") or "baja",
                }

    # Suplentes que entraron pero no estaban en el bench registrado (edge case)
    for pid, start in inc["subs_in"].items():
        if pid not in result:
            is_home = inc["player_side"].get(pid, True)
            result[pid] = {
                "mins":    max(1, round(final_min - start)),
                "status":  "sub_in",
                "is_home": is_home,
                "team_id": home_id if is_home else away_id,
                "name":    "",
            }

    return result


# ── Shotmap / zone analysis ───────────────────────────────────────────────────

def zone_from_y(y):
    """
    SofaScore normaliza los remates mirando hacia el mismo arco.
    y: 0 = costado izquierdo (del atacante), 100 = costado derecho.
    """
    if y is None:
        return "center"
    return "left" if y < 35 else "right" if y > 65 else "center"


def parse_shotmap(sm_data, home_id, away_id):
    """
    Retorna zona de ataque y goles por zona por equipo.
    {team_id: {attack_zones, goal_zones, sp_goals, open_goals, total_shots, total_goals}}
    """
    shots = (sm_data or {}).get("shotmap", [])
    init  = lambda: {"shots": Counter(), "goals": Counter(), "sp": 0, "op": 0}
    d     = {home_id: init(), away_id: init()}

    for s in shots:
        is_home = s.get("isHome", True)
        tid     = home_id if is_home else away_id
        coords  = s.get("playerCoordinates") or {}
        zone    = zone_from_y(coords.get("y"))
        stype   = s.get("shotType", "")
        sit     = s.get("situation", "")

        d[tid]["shots"][zone] += 1
        if stype == "goal":
            d[tid]["goals"][zone] += 1
            if sit in ("setpiece", "corner", "penalty"):
                d[tid]["sp"] += 1
            else:
                d[tid]["op"] += 1

    result = {}
    for tid in (home_id, away_id):
        td      = d[tid]
        ts      = sum(td["shots"].values()) or 1
        tg      = sum(td["goals"].values()) or 1
        result[str(tid)] = {
            "attack_zones": {z: round(td["shots"].get(z, 0) / ts, 3) for z in ("left", "center", "right")},
            "goal_zones":   {z: round(td["goals"].get(z, 0) / tg, 3) for z in ("left", "center", "right")},
            "sp_goals":     td["sp"],
            "open_goals":   td["op"],
            "total_shots":  sum(td["shots"].values()),
            "total_goals":  sum(td["goals"].values()),
        }
    return result


# ── Scraping per match ────────────────────────────────────────────────────────

def scrape_match(page, fx):
    eid       = fx["event_id"]
    home      = fx["home_name"]
    away      = fx["away_name"]
    home_id   = fx["home_id"]
    away_id   = fx["away_id"]
    score_h   = fx.get("score_home")
    score_a   = fx.get("score_away")
    group     = fx.get("group", "?")
    round_num = fx.get("round_num", "?")

    print(f"\n  [{group} F{round_num}] {home} {score_h}-{score_a} {away}  eid={eid}")

    lu_data = nav_json(page, f"{BASE}/event/{eid}/lineups")
    if not lu_data or "error" in lu_data:
        print("    → sin lineups, salteando")
        return None
    time.sleep(0.3)

    inc_raw    = nav_json(page, f"{BASE}/event/{eid}/incidents")
    inc_parsed = parse_incidents(inc_raw, home_id, away_id)
    time.sleep(0.3)

    player_mins = compute_player_minutes(lu_data, inc_parsed, home_id, away_id)

    # Stats por jugador
    player_stats = {}
    active = {pid: d for pid, d in player_mins.items() if d["mins"] >= 5}
    print(f"    → {len(active)} jugadores con minutos")

    for pid, pm in active.items():
        d = nav_json(page, f"{BASE}/event/{eid}/player/{pid}/statistics")
        if not d:
            time.sleep(0.2)
            continue
        st = (d.get("statistics") or {})

        xg_raw = st.get("expectedGoals")
        xa_raw = st.get("expectedAssists")
        goals  = st.get("goals") or 0
        xg = float(xg_raw) if xg_raw is not None else max(goals * 0.5, (st.get("totalShots") or 0) * 0.095)
        xa = float(xa_raw) if xa_raw is not None else (st.get("keyPass") or 0) * 0.08

        player_stats[str(pid)] = {
            "name":      pm["name"],
            "mins":      pm["mins"],
            "status":    pm["status"],
            "is_home":   pm["is_home"],
            "team_id":   pm["team_id"],
            "goals":     goals,
            "assists":   st.get("goalAssist") or 0,
            "yellow":    st.get("yellowCards") or 0,
            "red":       st.get("redCards") or 0,
            "rating":    st.get("rating"),
            "xg":        round(xg, 4),
            "xa":        round(xa, 4),
            "saves":     st.get("saves") or 0,
            "shots":     st.get("totalShots") or 0,
            "key_passes": st.get("keyPass") or 0,
        }
        time.sleep(0.25 + random.random() * 0.2)

    # Shotmap
    sm_raw   = nav_json(page, f"{BASE}/event/{eid}/shotmap")
    zones    = parse_shotmap(sm_raw, home_id, away_id)
    time.sleep(0.3)

    # Team stats
    ts_raw   = nav_json(page, f"{BASE}/event/{eid}/statistics")
    team_stats = {}
    for block in (ts_raw or {}).get("statistics", []):
        if block.get("period") == "ALL":
            for grp in block.get("groups", []):
                for item in grp.get("statisticsItems", []):
                    name = item.get("name", "")
                    team_stats[name] = {"home": item.get("home"), "away": item.get("away")}
    time.sleep(0.3)

    reds_home = [c for c in inc_parsed["cards"] if c["type"] in ("red","yellowRed") and c["is_home"]]
    reds_away = [c for c in inc_parsed["cards"] if c["type"] in ("red","yellowRed") and not c["is_home"]]
    if reds_home or reds_away:
        print(f"    → ROJAS: home={len(reds_home)} away={len(reds_away)}")
    if inc_parsed["missing_next"]:
        print(f"    → {len(inc_parsed['missing_next'])} suspendidos para siguiente fecha")

    return {
        "event_id":    eid,
        "home":        home,
        "away":        away,
        "home_id":     home_id,
        "away_id":     away_id,
        "group":       group,
        "round_num":   round_num,
        "timestamp":   fx.get("timestamp"),
        "score_home":  score_h,
        "score_away":  score_a,
        "player_stats": player_stats,
        "incidents": {
            "goals":        inc_parsed["goals"],
            "cards":        inc_parsed["cards"],
            "missing_next": inc_parsed["missing_next"],
        },
        "zones":       zones,
        "team_stats":  team_stats,
    }


# ── Lineups: bajas para siguiente fecha ───────────────────────────────────────

def update_lineups_suspensions(lineups, wc_matches, all_fixtures, player_db):
    """
    Para cada jugador con roja en el partido más reciente,
    lo agrega como 'missing' en el próximo partido de su equipo.
    """
    for eid_str, md in wc_matches.items():
        round_num = md.get("round_num", 0)
        home_id   = md.get("home_id")
        away_id   = md.get("away_id")

        for miss in md["incidents"].get("missing_next", []):
            pid     = miss.get("player_id")
            tid     = miss.get("team_id")
            reason  = miss.get("reason", "suspension")
            pid_str = str(pid)

            if not pid or not tid:
                continue

            # Buscar el partido siguiente de este equipo
            next_fx = None
            for fx in sorted(all_fixtures, key=lambda x: x.get("round_num", 99)):
                if fx.get("round_num", 0) <= round_num:
                    continue
                if fx.get("home_id") == tid or fx.get("away_id") == tid:
                    next_fx = fx
                    break

            if not next_fx:
                continue

            next_eid_str = str(next_fx["event_id"])
            if next_eid_str not in lineups:
                lineups[next_eid_str] = {
                    "event_id":  next_fx["event_id"],
                    "home":      next_fx["home_name"],
                    "away":      next_fx["away_name"],
                    "group":     next_fx.get("group", ""),
                    "round_num": next_fx.get("round_num"),
                    "confirmed": False,
                    "players":   {},
                }

            player_name = miss.get("player_name", "")
            if not player_name and pid_str in player_db:
                player_name = player_db[pid_str].get("name", "")

            lineups[next_eid_str]["players"][pid_str] = {
                "status":         "missing",
                "reason":         reason,
                "name":           player_name,
                "from_wc_result": True,
            }
            print(f"    → {player_name or pid_str} baja en {next_fx['home_name']} vs {next_fx['away_name']} ({reason})")

    return lineups


# ── Team profiles acumulados ─────────────────────────────────────────────────

def build_team_profiles(wc_matches, squads):
    """
    Acumula perfiles de ataque/defensa por selección usando todos sus partidos del Mundial.
    """
    tid_to_name = {td["team_id"]: tname for tname, td in squads.items()}

    raw = defaultdict(lambda: {
        "matches": 0, "goals_scored": 0, "goals_conceded": 0,
        "sp_scored": 0, "op_scored": 0, "sp_conceded": 0, "op_conceded": 0,
        "atk_zones": Counter(), "def_zones": Counter(),
    })

    for md in wc_matches.values():
        home_id   = md["home_id"]
        away_id   = md["away_id"]
        score_h   = md.get("score_home") or 0
        score_a   = md.get("score_away") or 0
        zones     = md.get("zones", {})

        for tid, opp_id, own_score, opp_score in [
            (home_id, away_id, score_h, score_a),
            (away_id, home_id, score_a, score_h),
        ]:
            p = raw[tid]
            p["matches"]         += 1
            p["goals_scored"]    += own_score
            p["goals_conceded"]  += opp_score

            z_own = zones.get(str(tid), {})
            z_opp = zones.get(str(opp_id), {})

            p["sp_scored"]    += z_own.get("sp_goals", 0)
            p["op_scored"]    += z_own.get("open_goals", 0)
            p["sp_conceded"]  += z_opp.get("sp_goals", 0)
            p["op_conceded"]  += z_opp.get("open_goals", 0)

            for zone, frac in (z_own.get("attack_zones") or {}).items():
                p["atk_zones"][zone] += frac
            for zone, frac in (z_opp.get("attack_zones") or {}).items():
                p["def_zones"][zone] += frac

    profiles = {}
    for tid, p in raw.items():
        tname = tid_to_name.get(tid, str(tid))
        n     = max(p["matches"], 1)
        gs    = max(p["goals_scored"], 1)
        gc    = max(p["goals_conceded"], 1)
        profiles[tname] = {
            "team_id":          tid,
            "wc_matches":       p["matches"],
            "goals_scored":     p["goals_scored"],
            "goals_conceded":   p["goals_conceded"],
            "sp_pct_scored":    round(p["sp_scored"]   / gs, 3),
            "op_pct_scored":    round(p["op_scored"]   / gs, 3),
            "sp_pct_conceded":  round(p["sp_conceded"] / gc, 3),
            "op_pct_conceded":  round(p["op_conceded"] / gc, 3),
            "attack_zones": {z: round(p["atk_zones"].get(z, 0) / n, 3) for z in ("left","center","right")},
            "defense_zones": {z: round(p["def_zones"].get(z, 0) / n, 3) for z in ("left","center","right")},
        }
    return profiles


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", type=int, default=None, help="Solo procesar fecha N de grupos")
    parser.add_argument("--force", action="store_true", help="Reprocesar partidos ya guardados")
    args = parser.parse_args()

    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures_raw = json.load(f)
    all_fixtures = fixtures_raw.get("fixtures", [])

    if args.fecha:
        target = [f for f in all_fixtures if f.get("round_num") == args.fecha]
    else:
        target = all_fixtures

    # Solo partidos con score (ya jugados)
    played = [f for f in target if f.get("score_home") is not None and f.get("score_away") is not None]
    if not played:
        print("No hay partidos jugados todavía.")
        return
    print(f"Partidos jugados: {len(played)}")

    # Cargar datos existentes
    wc_results = {"matches": {}, "team_profiles": {}}
    if WC_RESULTS_PATH.exists():
        with open(WC_RESULTS_PATH, encoding="utf-8") as f:
            wc_results = json.load(f)

    form_data = json.load(open(FORM_PATH, encoding="utf-8")) if FORM_PATH.exists() else {}
    lineups   = json.load(open(LINEUPS_PATH, encoding="utf-8")) if LINEUPS_PATH.exists() else {}
    player_db = json.load(open(PLAYER_PATH, encoding="utf-8")) if PLAYER_PATH.exists() else {}
    squads    = json.load(open(SQUADS_PATH, encoding="utf-8"))

    # player_id_int → pid_str para lookup rápido
    pid_set = set(player_db.keys())

    to_process = []
    for fx in played:
        eid_str = str(fx["event_id"])
        if not args.force and eid_str in wc_results["matches"]:
            print(f"  skip: {fx['home_name']} vs {fx['away_name']} (fecha {fx.get('round_num')})")
        else:
            to_process.append(fx)

    if not to_process:
        print("Todos los partidos ya están procesados. Usá --force para reprocesar.")
        return

    print(f"\nA procesar: {len(to_process)} partidos")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222", timeout=30000)
        ctx = browser.contexts[0]
        page = ctx.new_page()

        # Capturar x-requested-with desde requests reales de SofaScore
        captured = {}
        def on_req(req):
            if "/api/v1/player/" in req.url and "img." not in req.url:
                h = dict(req.headers)
                xrw = h.get("x-requested-with", "")
                if xrw and xrw != "441959":
                    captured["x-requested-with"] = xrw

        page.on("request", on_req)
        page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        page.evaluate("(() => { var b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Matches'); if(b)b.click(); })()")
        page.wait_for_timeout(3000)
        page.remove_listener("request", on_req)

        global _XREQUESTED
        _XREQUESTED = captured.get("x-requested-with", "441959")
        print(f"Chrome CDP | x-requested-with={_XREQUESTED} ({'capturado' if captured else 'default'})\n")

        for i, fx in enumerate(to_process, 1):
            print(f"\n[{i}/{len(to_process)}]", end="")
            md = scrape_match(page, fx)
            if not md:
                time.sleep(1)
                continue

            eid_str = str(fx["event_id"])
            wc_results["matches"][eid_str] = md

            # Actualizar form para cada jugador con minutos en este partido
            updated = 0
            for pid_str, pst in md["player_stats"].items():
                if pid_str not in pid_set:
                    continue
                mins = pst.get("mins", 0)
                if mins < 5:
                    continue

                goals = pst.get("goals", 0)
                xg    = max(float(pst.get("xg") or 0), goals * 0.5)
                xa    = float(pst.get("xa") or 0)

                entry = {
                    "event_id":   fx["event_id"],
                    "timestamp":  fx.get("timestamp"),
                    "tournament": "FIFA World Cup 2026",
                    "rating":     pst.get("rating"),
                    "mins":       mins,
                    "xg":         round(xg, 4),
                    "xa":         round(xa, 4),
                    "xg_direct":  pst.get("xg") is not None,
                    "goals":      goals,
                    "assists":    pst.get("assists", 0),
                    "is_wc":      True,
                    "weight":     WC_WEIGHT,
                }

                pdata     = player_db.get(pid_str, {})
                team_name = pdata.get("national_team", "")
                p_name    = pdata.get("name", pst.get("name", ""))

                if add_to_form(form_data, pid_str, entry, p_name, team_name):
                    updated += 1

            print(f"    → form: {updated} jugadores actualizados")

            # Guardar progresivamente
            with open(WC_RESULTS_PATH, "w", encoding="utf-8") as f:
                json.dump(wc_results, f, ensure_ascii=False, indent=2)
            with open(FORM_PATH, "w", encoding="utf-8") as f:
                json.dump(form_data, f, ensure_ascii=False, indent=2)

            time.sleep(1.0 + random.random() * 0.5)

        browser.close()

    # Bajas para próxima fecha (suspensiones por roja)
    print("\nProcesando suspensiones...")
    lineups = update_lineups_suspensions(lineups, wc_results["matches"], all_fixtures, player_db)

    # Perfiles de ataque/defensa acumulados
    wc_results["team_profiles"] = build_team_profiles(wc_results["matches"], squads)

    # Guardar todo
    with open(WC_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(wc_results, f, ensure_ascii=False, indent=2)
    with open(FORM_PATH, "w", encoding="utf-8") as f:
        json.dump(form_data, f, ensure_ascii=False, indent=2)
    with open(LINEUPS_PATH, "w", encoding="utf-8") as f:
        json.dump(lineups, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Partidos en wc_results: {len(wc_results['matches'])}")
    print(f"Jugadores en form:      {len(form_data)}")
    print(f"Equipos con perfil WC:  {len(wc_results['team_profiles'])}")

    if wc_results["team_profiles"]:
        print("\n  Perfil ATK/DEF por zona (desde partidos del Mundial):")
        print(f"  {'Selección':<25}  ATK: Izq  Cen  Der   DEF: Izq  Cen  Der")
        for tname, tp in sorted(wc_results["team_profiles"].items()):
            az = tp.get("attack_zones",  {})
            dz = tp.get("defense_zones", {})
            print(f"  {tname:<25}  "
                  f"     {az.get('left',0):.0%}  {az.get('center',0):.0%}  {az.get('right',0):.0%}"
                  f"        {dz.get('left',0):.0%}  {dz.get('center',0):.0%}  {dz.get('right',0):.0%}")


if __name__ == "__main__":
    main()
