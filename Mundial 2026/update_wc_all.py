#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_wc_all.py — Actualización completa en una sola sesión CDP.
1. Captura x-captcha token (igual que form_v4)
2. Actualiza squads desde SofaScore (detecta reemplazos)
3. Scrapea stats de jugadores nuevos
4. Actualiza form de jugadores nuevos
"""

import json, time, random, sys, io, math
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE          = "https://www.sofascore.com/api/v1"
WC_SEASON_ID  = 58210
BASE_DIR      = Path(__file__).parent
SQUADS_PATH   = BASE_DIR / "wc2026_squads.json"
STATS_PATH    = BASE_DIR / "wc2026_player_stats.json"
FORM_PATH     = BASE_DIR / "wc2026_form.json"

CDP_URL       = "http://localhost:9222"
N_MATCHES     = 10
DECAY         = 0.82
MIN_CLUB_MINS = 200


# ── Helpers ──────────────────────────────────────────────────────────────────

def api_call(page, url, xrw, retries=3):
    for attempt in range(retries):
        try:
            result = page.evaluate(f"""async () => {{
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
            }}""")
            if not result:
                time.sleep(1)
                continue
            data = json.loads(result)
            if "error" in data and "events" not in data and "statistics" not in data:
                time.sleep(2 + attempt * 2)
                continue
            return data
        except Exception as e:
            time.sleep(2)
    return None


def setup_page(pw):
    """Conecta a Chrome, navega a SofaScore, captura x-requested-with del primer request."""
    browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=10000)
    ctx     = browser.contexts[0]

    # Usar página existente o crear una nueva
    sofa = [p for p in ctx.pages if "sofascore.com/football/player" in p.url]
    page = sofa[0] if sofa else ctx.new_page()

    # Capturar x-requested-with del primer request de la página
    xrw_cap = {}
    def on_req(r):
        if "sofascore.com/api/v1/player" in r.url and "events/last" in r.url:
            xrw_cap.update(dict(r.headers))
    page.on("request", on_req)

    if not sofa or "player" not in page.url:
        page.goto("https://www.sofascore.com/football/player/erling-haaland/839956",
                  wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)
    page.remove_listener("request", on_req)

    xrw = xrw_cap.get("x-requested-with", "441959")
    print(f"x-requested-with: {xrw}")
    return browser, page, xrw


# ── 1. Update squads ─────────────────────────────────────────────────────────

def update_squads(page, xrw, squads):
    print("\n[SQUADS] Actualizando planteles desde SofaScore...")
    new_players = {}  # team -> list of new player dicts

    for team_name, tdata in squads.items():
        team_id = tdata["team_id"]
        url = f"{BASE}/team/{team_id}/players?season={WC_SEASON_ID}"
        data = api_call(page, url, xrw)
        if not data:
            # Fallback: unique-tournament squad endpoint
            url2 = f"{BASE}/unique-tournament/16/season/{WC_SEASON_ID}/team/{team_id}/players"
            data = api_call(page, url2, xrw)
        if not data:
            continue

        current_ids = {p["id"] for p in tdata["players"]}
        fresh_players = data.get("players", []) or data.get("data", [])

        added = []
        for fp in fresh_players:
            pid = fp.get("player", {}).get("id") or fp.get("id")
            if pid and pid not in current_ids:
                pname = fp.get("player", {}).get("name") or fp.get("name", "?")
                pos   = fp.get("player", {}).get("position", {})
                if isinstance(pos, dict):
                    pos = pos.get("name", "M")
                added.append({"id": pid, "name": pname, "position": pos})
                tdata["players"].append({"id": pid, "name": pname, "position": pos, "jerseyNumber": ""})

        # Eliminar jugadores que ya no están en el squad oficial
        fresh_ids = {fp.get("player", {}).get("id") or fp.get("id") for fp in fresh_players}
        if fresh_ids:
            removed = [p for p in tdata["players"] if p["id"] not in fresh_ids]
            tdata["players"] = [p for p in tdata["players"] if p["id"] in fresh_ids]
        else:
            removed = []

        if added:
            print(f"  {team_name}: +{len(added)} nuevos — {[p['name'] for p in added]}")
            new_players[team_name] = added
        if removed:
            print(f"  {team_name}: -{len(removed)} removidos — {[p['name'] for p in removed]}")

        time.sleep(0.4)

    # Guardar squads actualizados
    with open(SQUADS_PATH, "w", encoding="utf-8") as f:
        json.dump(squads, f, ensure_ascii=False, indent=2)
    print(f"[SQUADS] Guardado: {SQUADS_PATH}")
    return new_players


# ── 2. Player stats para jugadores nuevos ────────────────────────────────────

def get_player_stats(page, player_id, national_team_id, xrw):
    # Últimos eventos
    all_events = []
    for pg in range(3):
        data = api_call(page, f"{BASE}/player/{player_id}/events/last/{pg}", xrw)
        if not data or not data.get("events"):
            break
        all_events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.3)

    if not all_events:
        return None, None

    # Club stats: torneo más frecuente (excluyendo selección)
    club_events = [e for e in all_events
                   if e.get("homeTeam", {}).get("id") != national_team_id
                   and e.get("awayTeam", {}).get("id") != national_team_id]

    club_stats = None
    club_team  = ""
    if club_events:
        tour_c = Counter()
        for e in club_events:
            ut = e.get("tournament", {}).get("uniqueTournament", {})
            s  = e.get("season", {})
            if ut.get("id") and s.get("id"):
                tour_c[(ut["id"], s["id"], ut.get("name",""))] += 1
        if tour_c:
            (ut_id, s_id, t_name), _ = tour_c.most_common(1)[0]
            url = f"{BASE}/player/{player_id}/unique-tournament/{ut_id}/season/{s_id}/statistics/overall"
            sdata = api_call(page, url, xrw)
            if sdata and "statistics" in sdata:
                raw = sdata["statistics"]
                mins  = raw.get("minutesPlayed") or raw.get("minutesPlayed") or 0
                games = raw.get("appearances") or raw.get("games") or 0
                goals = raw.get("goals") or 0
                asists= raw.get("goalAssist") or 0
                shots = raw.get("totalShots") or 0
                kp    = raw.get("keyPass") or 0
                xg    = float(raw.get("expectedGoals") or shots * 0.095)
                xa    = float(raw.get("expectedAssists") or kp * 0.08)
                yel   = raw.get("yellowCards") or 0
                saves = raw.get("saves") or 0
                vi    = raw.get("cleanSheets") or 0
                gc    = raw.get("goalsConceded") or 0
                team_ids = Counter(
                    e.get("homeTeam" if e.get("homeTeam",{}).get("id") != national_team_id else "awayTeam",{}).get("id")
                    for e in club_events
                    if e.get("tournament",{}).get("uniqueTournament",{}).get("id") == ut_id
                )
                # Find club name
                for e in club_events:
                    for side in ("homeTeam","awayTeam"):
                        if e.get(side,{}).get("id") == (team_ids.most_common(1) or [(None,)])[0][0]:
                            club_team = e.get(side,{}).get("name","")
                            break
                    if club_team:
                        break
                club_stats = {
                    "Minutos Jugados": mins, "Partidos Jugados": games,
                    "Goles": goals, "Asistencias": asists, "Amarillas": yel,
                    "xG": round(xg, 4), "xA": round(xa, 4),
                    "Remates Totales": shots, "Pases Clave": kp,
                    "Vallas Invictas": vi, "Goles Recibidos": gc, "Atajadas": saves,
                }

    # Intl stats
    intl_events = [e for e in all_events
                   if e.get("homeTeam",{}).get("id") == national_team_id
                   or e.get("awayTeam",{}).get("id") == national_team_id]
    intl_stats  = None
    if intl_events:
        totals = defaultdict(float)
        for ev in intl_events[:20]:
            eid = ev.get("id")
            if not eid: continue
            sd = api_call(page, f"{BASE}/event/{eid}/player/{player_id}/statistics", xrw)
            st = (sd or {}).get("statistics", {})
            if not st.get("minutesPlayed"):
                continue
            totals["mins"]   += st.get("minutesPlayed") or 0
            totals["games"]  += 1
            totals["goals"]  += st.get("goals") or 0
            totals["asists"] += st.get("goalAssist") or 0
            totals["shots"]  += st.get("totalShots") or 0
            totals["kp"]     += st.get("keyPass") or 0
            totals["xg"]     += float(st.get("expectedGoals") or (totals["shots"] * 0.095))
            totals["xa"]     += float(st.get("expectedAssists") or (totals["kp"] * 0.08))
            totals["yel"]    += st.get("yellowCards") or 0
            time.sleep(0.3)
        if totals["games"] > 0:
            intl_stats = {
                "Minutos Jugados": int(totals["mins"]), "Partidos Jugados": int(totals["games"]),
                "Goles": int(totals["goals"]), "Asistencias": int(totals["asists"]),
                "Amarillas": int(totals["yel"]),
                "xG": round(totals["xg"], 4), "xA": round(totals["xa"], 4),
                "Remates Totales": int(totals["shots"]), "Pases Clave": int(totals["kp"]),
            }

    return club_stats, intl_stats


# ── 3. Form para jugadores nuevos ────────────────────────────────────────────

def get_form(page, player_id, national_team_id, xrw):
    all_events = []
    for pg in range(5):
        data = api_call(page, f"{BASE}/player/{player_id}/events/last/{pg}", xrw)
        if not data or not data.get("events"):
            break
        all_events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.3)

    intl_events = [e for e in all_events
                   if e.get("homeTeam",{}).get("id") == national_team_id
                   or e.get("awayTeam",{}).get("id") == national_team_id]
    intl_events.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)

    matches = []
    for ev in intl_events[:N_MATCHES * 3]:
        if len(matches) >= N_MATCHES:
            break
        eid = ev.get("id")
        if not eid:
            continue
        sd   = api_call(page, f"{BASE}/event/{eid}/player/{player_id}/statistics", xrw)
        st   = (sd or {}).get("statistics", {})
        mins = st.get("minutesPlayed") or 0
        if mins == 0:
            continue
        xg = float(st.get("expectedGoals") or (st.get("totalShots") or 0) * 0.095)
        xa = float(st.get("expectedAssists") or (st.get("keyPass") or 0) * 0.08)
        matches.append({
            "event_id": eid,
            "timestamp": ev.get("startTimestamp"),
            "rating": st.get("rating"),
            "mins": mins, "xg": round(xg, 4), "xa": round(xa, 4),
            "goals": st.get("goals") or 0, "assists": st.get("goalAssist") or 0,
        })
        time.sleep(0.4 + random.random() * 0.3)

    if not matches:
        return None

    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        if m["mins"] < 20:
            continue
        w = DECAY ** i
        w_xg    += (m["xg"] / m["mins"] * 90) * w
        w_xa    += (m["xa"] / m["mins"] * 90) * w
        total_w += w
    form_stats = {"form_xg_90": round(w_xg/total_w, 4), "form_xa_90": round(w_xa/total_w, 4), "n": len(matches)} if total_w > 0 else None
    return {"matches": matches, "form": form_stats}


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright

    squads   = json.load(open(SQUADS_PATH, encoding="utf-8"))
    stats    = json.load(open(STATS_PATH, encoding="utf-8")) if STATS_PATH.exists() else {}
    form     = json.load(open(FORM_PATH, encoding="utf-8")) if FORM_PATH.exists() else {}

    existing_ids = set(stats.keys())

    with sync_playwright() as pw:
        print("Conectando a Chrome y configurando página...")
        browser, page, xrw = setup_page(pw)

        # Verificar API
        test = api_call(page, f"{BASE}/player/839956/events/last/0", xrw)
        if not test or test.get("error"):
            print(f"ERROR: API no responde — {test}")
            return
        print(f"API OK — {len(test.get('events',[]))} eventos Haaland\n")

        # ── 1. Update squads ──────────────────────────────────────────────────
        new_by_team = update_squads(page, xrw, squads)

        # Construir lista de jugadores nuevos que necesitan stats
        new_players = []
        for team_name, players in new_by_team.items():
            team_id = squads[team_name]["team_id"]
            group   = squads[team_name]["group"]
            for p in players:
                new_players.append({
                    "player_id": p["id"], "name": p["name"],
                    "position": p.get("position","M"),
                    "national_team": team_name,
                    "national_team_id": team_id,
                    "group": group,
                })

        # También procesar jugadores que ya están en squads pero NO en stats
        for team_name, tdata in squads.items():
            for p in tdata["players"]:
                pid_str = str(p["id"])
                if pid_str not in existing_ids:
                    new_players.append({
                        "player_id": p["id"], "name": p["name"],
                        "position": p.get("position","M"),
                        "national_team": team_name,
                        "national_team_id": tdata["team_id"],
                        "group": tdata["group"],
                    })

        # Deduplicar
        seen = set()
        unique_new = []
        for p in new_players:
            if p["player_id"] not in seen:
                seen.add(p["player_id"])
                unique_new.append(p)

        print(f"\n[STATS] Jugadores nuevos a scrapear: {len(unique_new)}")

        # ── 2. Stats para jugadores nuevos ───────────────────────────────────
        for i, p in enumerate(unique_new, 1):
            pid_str = str(p["player_id"])
            print(f"  [{i}/{len(unique_new)}] {p['name']} ({p['national_team']})", end=" ", flush=True)
            cs, ist = get_player_stats(page, p["player_id"], p["national_team_id"], xrw)
            if cs:
                print(f"club={cs.get('Minutos Jugados')}min xG={cs.get('xG'):.2f}", end=" ")
            if ist:
                print(f"intl={ist.get('Partidos Jugados')}PJ", end=" ")
            if cs or ist:
                print()
                stats[pid_str] = {
                    "name":             p["name"],
                    "position":         p["position"],
                    "national_team":    p["national_team"],
                    "national_team_id": p["national_team_id"],
                    "group":            p["group"],
                    "jersey":           None,
                    "club_team":        "",
                    "club_stats":       cs,
                    "intl_stats":       ist,
                }
            else:
                print("sin datos")
            time.sleep(0.8 + random.random() * 0.5)

        # Guardar stats
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n[STATS] Guardado: {STATS_PATH} ({len(stats)} jugadores)")

        # ── 3. Form para jugadores nuevos ─────────────────────────────────────
        print(f"\n[FORM] Actualizando form para {len(unique_new)} jugadores nuevos...")
        updated_form = 0
        for i, p in enumerate(unique_new, 1):
            pid_str = str(p["player_id"])
            print(f"  [{i}/{len(unique_new)}] {p['name']}", end=" ", flush=True)
            fm = get_form(page, p["player_id"], p["national_team_id"], xrw)
            if fm:
                form[pid_str] = {"name": p["name"], "team": p["national_team"], **fm}
                print(f"→ {len(fm['matches'])} partidos")
                updated_form += 1
            else:
                print("→ sin partidos")
            time.sleep(0.8 + random.random() * 0.5)

        with open(FORM_PATH, "w", encoding="utf-8") as f:
            json.dump(form, f, ensure_ascii=False, indent=2)
        print(f"\n[FORM] Guardado: {FORM_PATH} ({updated_form} actualizados)")
        print("\nDone.")


if __name__ == "__main__":
    main()
