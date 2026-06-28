#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrape 4 missing F1 matches via pychrome CDP."""
import pychrome, json, time, sys, random, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE          = "https://www.sofascore.com/api/v1"
CDP_PORT      = "http://localhost:9222"
MISSING_EIDS  = [
    # F1 — re-scrapear todos los partidos con bug de minutesPlayed (scraper viejo asignaba
    # 90min a todos los jugadores del squad, incluso los que no jugaron)
    15186501,  # France vs Senegal
    15186526,  # Qatar vs Switzerland
    15186710,  # Mexico vs South Africa
    15186720,  # South Korea vs Czechia
    15186751,  # Austria vs Jordan
    15186773,  # Iraq vs Norway
    15186783,  # Spain vs Cabo Verde
    15186811,  # Saudi Arabia vs Uruguay
    15186832,  # Iran vs New Zealand
    15186836,  # Canada vs Bosnia & Herzegovina
    15186837,  # Belgium vs Egypt
    15186850,  # Brazil vs Morocco
    15186853,  # Haiti vs Scotland
    15186854,  # Argentina vs Algeria
    15186873,  # USA vs Paraguay
    15186874,  # Australia vs Türkiye
    15186899,  # Germany vs Curaçao
    15186904,  # Côte d'Ivoire vs Ecuador
    15186945,  # Netherlands vs Japan
    15186951,  # Sweden vs Tunisia
]
BASE_DIR      = Path(__file__).parent
FIXTURES_PATH = BASE_DIR / "wc2026_fixtures.json"
WC_RESULTS    = BASE_DIR / "wc2026_wc_results.json"
FORM_PATH     = BASE_DIR / "wc2026_form.json"

DECAY     = 0.82
WC_WEIGHT = 3
N_FORM    = 20


def get_tab():
    browser = pychrome.Browser(url=CDP_PORT)
    for t in browser.list_tab():
        url = t._kwargs.get("url", "")
        if "sofascore.com" in url and "sync" not in url and "pixel" not in url:
            return t
    raise RuntimeError("No SofaScore tab found")


def api(tab, url, retries=3):
    js = (
        "(async () => { try { const r = await fetch('" + url + "', {"
        "credentials:'include', headers:{'x-requested-with':'441959','Accept':'application/json'}"
        "}); return await r.text(); } catch(e) { return JSON.stringify({error:e.toString()}); } })()"
    )
    for _ in range(retries):
        try:
            res = tab.call_method("Runtime.evaluate", expression=js,
                                  awaitPromise=True, returnByValue=True, timeout=20)
            raw = res.get("result", {}).get("value", "")
            if raw:
                d = json.loads(raw)
                if "error" not in d:
                    return d
        except Exception as e:
            print(f"    warn: {e}")
        time.sleep(2)
    return None


def parse_incidents(incidents, home_id, away_id):
    final_min = 90
    for inc in incidents:
        if inc.get("incidentType") == "period" and inc.get("text") in ("FT", "AP", "AET"):
            t = inc.get("time", 90); at = inc.get("addedTime") or 0
            final_min = max(final_min, t + at)

    subs_out, subs_in, player_side = {}, {}, {}
    goals, cards, missing_next = [], [], []

    for inc in incidents:
        itype = inc.get("incidentType")
        is_h  = inc.get("isHome", True)
        if itype == "substitution":
            minute = inc.get("time", 90) + (inc.get("addedTime") or 0) * 0.5
            pid_out = (inc.get("playerOut") or {}).get("id")
            pid_in  = (inc.get("playerIn")  or {}).get("id")
            if pid_out:
                subs_out[pid_out] = min(subs_out.get(pid_out, minute), minute)
                player_side[pid_out] = is_h
            if pid_in:
                subs_in[pid_in] = minute
                player_side[pid_in] = is_h
        elif itype in ("goal", "ownGoal") and not inc.get("rescinded"):
            minute = inc.get("time", 0) + (inc.get("addedTime") or 0) * 0.5
            cls    = inc.get("incidentClass", "")
            player = inc.get("player") or {}
            goals.append({
                "minute": minute, "player_id": player.get("id"),
                "player_name": player.get("name", ""),
                "team_id": home_id if is_h else away_id, "is_home": is_h,
                "type": "set_piece" if cls in ("fromSetPiece", "fromCorner", "penalty") else "open_play",
                "is_penalty": cls == "penalty", "is_own_goal": itype == "ownGoal",
            })
        elif itype == "card":
            player = inc.get("player") or {}
            pid    = player.get("id")
            cls    = inc.get("incidentClass", "")
            cards.append({"player_id": pid, "player_name": player.get("name", ""),
                          "team_id": home_id if is_h else away_id,
                          "is_home": is_h, "type": cls, "minute": inc.get("time", 0)})
            if cls in ("red", "yellowRed"):
                missing_next.append({"player_id": pid, "player_name": player.get("name", ""),
                                     "team_id": home_id if is_h else away_id,
                                     "is_home": is_h, "reason": "suspension"})

    return final_min, subs_out, subs_in, goals, cards, missing_next


def compute_player_mins(lu_data, subs_out, subs_in, final_min, home_id, away_id):
    result = {}
    if not lu_data:
        return result
    for side in ("home", "away"):
        is_h = side == "home"
        tid  = home_id if is_h else away_id
        sd   = (lu_data or {}).get(side) or {}
        for p in (sd.get("players") or []):
            player = p.get("player") or {}
            pid    = player.get("id")
            if not pid: continue
            end_min = subs_out.get(pid, final_min)
            result[pid] = {"mins": max(1, round(end_min)), "status": "starter",
                           "is_home": is_h, "team_id": tid, "name": player.get("name", "")}
        for key in ("substitutes", "bench"):
            for p in (sd.get(key) or []):
                player = p.get("player") or {}
                pid    = player.get("id")
                if not pid: continue
                if pid in subs_in:
                    start = subs_in[pid]
                    result[pid] = {"mins": max(1, round(final_min - start)), "status": "sub_in",
                                   "is_home": is_h, "team_id": tid, "name": player.get("name", "")}
    # Edge case: subs_in players not found in lineup
    for pid, start in subs_in.items():
        if pid not in result:
            is_h = True  # fallback
            result[pid] = {"mins": max(1, round(final_min - start)), "status": "sub_in",
                           "is_home": is_h, "team_id": home_id, "name": ""}
    return result


def form_stats(matches):
    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        if (m.get("mins") or 0) < 20: continue
        w = (DECAY ** i) * m.get("weight", 1.0)
        mins = m["mins"]
        w_xg    += (m.get("xg", 0) / mins * 90) * w
        w_xa    += (m.get("xa", 0) / mins * 90) * w
        total_w += w
    if total_w == 0: return None
    return {"form_xg_90": round(w_xg / total_w, 4),
            "form_xa_90": round(w_xa / total_w, 4),
            "n": len([m for m in matches if (m.get("mins") or 0) >= 20])}


def main():
    tab = get_tab()
    tab.start()

    fixtures  = json.load(open(FIXTURES_PATH, encoding="utf-8"))["fixtures"]
    fx_by_eid = {f["event_id"]: f for f in fixtures}
    wc_data   = json.load(open(WC_RESULTS, encoding="utf-8"))
    form_data = json.load(open(FORM_PATH, encoding="utf-8")) if FORM_PATH.exists() else {}
    import time as _t
    now_ts = int(_t.time())

    for eid in MISSING_EIDS:
        fx = fx_by_eid.get(eid, {})
        home    = fx.get("home_name", "?")
        away    = fx.get("away_name", "?")
        home_id = fx.get("home_id")
        away_id = fx.get("away_id")
        sh      = fx.get("score_home")
        sa      = fx.get("score_away")
        group   = fx.get("group", "?")

        # Obtener score desde API si no está en fixtures
        if sh is None or sa is None:
            ev_data = api(tab, f"{BASE}/event/{eid}")
            if ev_data and ev_data.get("event"):
                ev = ev_data["event"]
                sh = ev.get("homeScore", {}).get("current")
                sa = ev.get("awayScore", {}).get("current")
                if not home_id:
                    home_id = ev.get("homeTeam", {}).get("id")
                    away_id = ev.get("awayTeam", {}).get("id")
                    home    = ev.get("homeTeam", {}).get("name", home)
                    away    = ev.get("awayTeam", {}).get("name", away)
                time.sleep(0.3)
        print(f"\n[{group} F1] {home} {sh}-{sa} {away}  eid={eid}")

        lu_data  = api(tab, f"{BASE}/event/{eid}/lineups")
        time.sleep(0.3)
        inc_raw  = api(tab, f"{BASE}/event/{eid}/incidents")
        time.sleep(0.3)

        incidents = (inc_raw or {}).get("incidents", [])
        final_min, subs_out, subs_in, goals, cards, missing_next = parse_incidents(
            incidents, home_id, away_id)

        player_mins = compute_player_mins(lu_data, subs_out, subs_in, final_min, home_id, away_id)
        # Todos los jugadores potencialmente activos (incluye bench, filtramos después por minutesPlayed)
        active      = {pid: d for pid, d in player_mins.items()}
        print(f"    {len(active)} jugadores candidatos  final_min={final_min}")

        player_stats = {}
        starters_counted = {True: 0, False: 0}
        for pid, pm in active.items():
            d = api(tab, f"{BASE}/event/{eid}/player/{pid}/statistics")
            if not d:
                time.sleep(0.2)
                continue
            st      = d.get("statistics") or {}
            # Usar minutesPlayed de la API (fuente de verdad) en lugar del valor computado
            actual_mins = st.get("minutesPlayed") or 0
            if actual_mins == 0:
                continue  # no jugó, omitir
            # Clasificar: titular si jugó ≥60 min, sub_in si jugó menos
            is_h = pm["is_home"]
            if pid in subs_in:
                player_status = "sub_in"
            elif actual_mins >= 60:
                player_status = "starter"
                starters_counted[is_h] += 1
            else:
                player_status = "sub_in"
            xg_raw  = st.get("expectedGoals")
            xa_raw  = st.get("expectedAssists")
            goals_p = st.get("goals") or 0
            xg = float(xg_raw) if xg_raw is not None else max(goals_p * 0.5, (st.get("totalShots") or 0) * 0.095)
            xa = float(xa_raw) if xa_raw is not None else (st.get("keyPass") or 0) * 0.08

            pid_str = str(pid)
            player_stats[pid_str] = {
                "name":       pm["name"],
                "mins":       actual_mins,
                "status":     player_status,
                "is_home":    pm["is_home"],
                "team_id":    pm["team_id"],
                "goals":      goals_p,
                "assists":    st.get("goalAssist") or 0,
                "yellow":     st.get("yellowCards") or 0,
                "red":        st.get("redCards") or 0,
                "rating":     st.get("rating"),
                "xg":         round(xg, 4),
                "xa":         round(xa, 4),
                "saves":      st.get("saves") or 0,
                "shots":      st.get("totalShots") or 0,
                "key_passes": st.get("keyPass") or 0,
            }

            # Actualizar form
            form_entry = {
                "event_id": eid, "mins": pm["mins"],
                "xg": round(xg, 4), "xa": round(xa, 4),
                "goals": goals_p, "weight": WC_WEIGHT,
            }
            fd = form_data.setdefault(pid_str, {"name": pm["name"], "team": "", "matches": []})
            existing_eids = {m.get("event_id") for m in fd.get("matches", [])}
            if eid not in existing_eids:
                matches = [form_entry] + fd.get("matches", [])
                fd["matches"] = matches[:N_FORM]
                nf = form_stats(fd["matches"])
                if nf:
                    fd["form"] = nf
                fd["v2"] = True

            time.sleep(0.25 + random.random() * 0.15)

        wc_data["matches"][str(eid)] = {
            "event_id":   eid,
            "home":       home,
            "away":       away,
            "home_id":    home_id,
            "away_id":    away_id,
            "group":      group,
            "round_num":  fx.get("round_num", 1),
            "timestamp":  fx.get("timestamp"),
            "score_home": sh,
            "score_away": sa,
            "player_stats": player_stats,
            "incidents": {
                "goals":        goals,
                "cards":        cards,
                "missing_next": missing_next,
            },
            "zones":      {},
            "team_stats": {},
        }

        print(f"    Guardado: {len(player_stats)} jugadores  (home starters={starters_counted[True]}, away starters={starters_counted[False]})")
        if missing_next:
            for m in missing_next:
                print(f"    SUSPENSION: {m['player_name']} ({home if m['is_home'] else away})")

        time.sleep(0.5)

    tab.stop()

    json.dump(wc_data, open(WC_RESULTS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(form_data, open(FORM_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwc_results: {len(wc_data['matches'])} partidos totales")
    print(f"form_data:  {len(form_data)} jugadores")


if __name__ == "__main__":
    main()
