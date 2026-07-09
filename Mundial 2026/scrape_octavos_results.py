#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_octavos_results.py — Scrape resultados + stats de jugadores de Octavos (Round of 16).

1. Descubre event_ids reales desde SofaScore para los Octavos
2. Matchea con los cruces de wc2026_knockout.json (ko_data["cuartos"])
3. Scrape scores + player stats de los partidos ya terminados
4. Actualiza wc2026_wc_results.json + wc2026_form.json
5. Actualiza ko_data["cuartos"] con resultados reales
6. Rebuild modelo DC → bracket → analytics
"""
import pychrome, json, time, random, sys, io, subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE         = "https://www.sofascore.com/api/v1"
CDP_PORT     = "http://localhost:9222"
BASE_DIR     = Path(__file__).parent
KO_PATH      = BASE_DIR / "wc2026_knockout.json"
WC_RESULTS   = BASE_DIR / "wc2026_wc_results.json"
FORM_PATH    = BASE_DIR / "wc2026_form.json"

WC_UNIQUE_TOURNAMENT_ID = 16
WC_SEASON_ID = 58210
DECAY        = 0.82
WC_WEIGHT    = 20   # Octavos: peso alto, es la fecha más reciente
N_FORM       = 20
ROUND_NUM    = 5    # Octavos = Round of 16 en nuestro sistema

# Si se conocen los event IDs hardcodeados de SofaScore, agregarlos acá.
# Si están vacíos, el script los descubre automáticamente desde la API.
# Formato: {event_id: {"home": "Team A", "away": "Team B", "sh": 0, "sa": 0, "pens": None}}
KO_OCTAVOS_EIDS = {
    12812990: {"home": "Portugal",     "away": "Spain",      "sh": 0, "sa": 1, "pens": None},
    12812991: {"home": "Switzerland",  "away": "Colombia",   "sh": 4, "sa": 3, "pens": None},
    12812993: {"home": "Argentina",    "away": "Egypt",      "sh": 3, "sa": 2, "pens": None},
    12813002: {"home": "USA",          "away": "Belgium",    "sh": 1, "sa": 4, "pens": None},
    12813006: {"home": "Brazil",       "away": "Norway",     "sh": 1, "sa": 2, "pens": None},
    12813007: {"home": "Mexico",       "away": "England",    "sh": 2, "sa": 3, "pens": None},
    12813009: {"home": "Canada",       "away": "Morocco",    "sh": 0, "sa": 3, "pens": None},
    12813010: {"home": "Paraguay",     "away": "France",     "sh": 0, "sa": 1, "pens": None},
}


def get_tab():
    browser = pychrome.Browser(url=CDP_PORT)
    for t in browser.list_tab():
        url = t._kwargs.get("url", "")
        if "sofascore.com" in url and "sync" not in url and "pixel" not in url:
            return t
    raise RuntimeError("No SofaScore tab found — abrí SofaScore en Chrome")


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


def normalize(name):
    return (name.lower()
            .replace("&", "and")
            .replace("côte d'ivoire", "ivory coast")
            .replace("cote d'ivoire", "ivory coast")
            .replace("usa", "united states")
            .strip())


def normalize_team(name):
    """Normalización más agresiva para comparación entre SofaScore y nuestros datos."""
    aliases = {
        "united states": "usa",
        "united states of america": "usa",
        "bosnia & herzegovina": "bosnia and herzegovina",
        "korea republic": "south korea",
        "republic of ireland": "ireland",
        "dr congo": "democratic republic of the congo",
        "congo dr": "democratic republic of the congo",
    }
    n = normalize(name)
    return aliases.get(n, n)


def discover_octavos(tab, cuartos_teams):
    """
    Descubre los event IDs de Octavos consultando SofaScore.
    Intenta distintos round numbers de la unique-tournament API.
    """
    print("[1] Descubriendo event IDs de Octavos desde SofaScore...")
    found = {}

    cuartos_normalized = set()
    for t in cuartos_teams:
        cuartos_normalized.add(normalize_team(t))

    # Intentar rounds 4-8 en la unique-tournament API
    for round_n in range(4, 10):
        url = f"{BASE}/unique-tournament/{WC_UNIQUE_TOURNAMENT_ID}/season/{WC_SEASON_ID}/events/round/{round_n}"
        data = api(tab, url)
        if not data:
            continue
        events = data.get("events", [])
        if not events:
            continue

        ko_events = []
        for ev in events:
            status = (ev.get("status") or {}).get("type", "")
            ht = (ev.get("homeTeam") or {}).get("name", "")
            at = (ev.get("awayTeam") or {}).get("name", "")
            hn = normalize_team(ht)
            an = normalize_team(at)
            # Es un Octavos si ambos equipos están en nuestro bracket de cuartos
            if hn in cuartos_normalized or an in cuartos_normalized:
                ko_events.append(ev)

        if ko_events:
            print(f"  Round {round_n}: {len(ko_events)} eventos KO encontrados")
            for ev in ko_events:
                eid   = ev["id"]
                ht    = (ev.get("homeTeam") or {}).get("name", "")
                at    = (ev.get("awayTeam") or {}).get("name", "")
                hid   = (ev.get("homeTeam") or {}).get("id")
                aid   = (ev.get("awayTeam") or {}).get("id")
                status = (ev.get("status") or {}).get("type", "")
                hsc   = (ev.get("homeScore") or {}).get("current")
                asc   = (ev.get("awayScore") or {}).get("current")

                # Detectar penales
                pens_winner = None
                hpen = (ev.get("homeScore") or {}).get("penalties")
                apen = (ev.get("awayScore") or {}).get("penalties")
                if hpen is not None and apen is not None:
                    pens_winner = "home" if hpen > apen else "away"

                found[eid] = {
                    "home": ht, "away": at,
                    "home_id": hid, "away_id": aid,
                    "sh": hsc, "sa": asc,
                    "status": status, "pens": pens_winner,
                    "sofascore_round": round_n,
                }
                print(f"    eid={eid}  {ht} {hsc}-{asc} {at}  status={status}  pens={pens_winner}")

        time.sleep(0.3)

    if not found:
        print("  No se encontraron eventos vía round discovery — intentando fecha-based...")
        # Fallback: buscar por fechas (July 7-9, 2026)
        for date_str in ["2026-07-07", "2026-07-08", "2026-07-09"]:
            url = f"{BASE}/sport/football/scheduled-events/{date_str}"
            data = api(tab, url)
            if not data:
                continue
            for ev in (data.get("events") or []):
                ut_id = (ev.get("tournament", {}).get("uniqueTournament") or {}).get("id")
                if ut_id != WC_UNIQUE_TOURNAMENT_ID:
                    continue
                eid  = ev["id"]
                ht   = (ev.get("homeTeam") or {}).get("name", "")
                at   = (ev.get("awayTeam") or {}).get("name", "")
                hid  = (ev.get("homeTeam") or {}).get("id")
                aid  = (ev.get("awayTeam") or {}).get("id")
                hsc  = (ev.get("homeScore") or {}).get("current")
                asc  = (ev.get("awayScore") or {}).get("current")
                status = (ev.get("status") or {}).get("type", "")
                pens_winner = None
                hpen = (ev.get("homeScore") or {}).get("penalties")
                apen = (ev.get("awayScore") or {}).get("penalties")
                if hpen is not None and apen is not None:
                    pens_winner = "home" if hpen > apen else "away"
                hn = normalize_team(ht)
                an = normalize_team(at)
                if hn in cuartos_normalized or an in cuartos_normalized:
                    found[eid] = {
                        "home": ht, "away": at,
                        "home_id": hid, "away_id": aid,
                        "sh": hsc, "sa": asc,
                        "status": status, "pens": pens_winner,
                        "sofascore_round": 0,
                    }
                    print(f"    [{date_str}] eid={eid}  {ht} {hsc}-{asc} {at}  status={status}")
            time.sleep(0.3)

    return found


def parse_incidents(incidents, home_id, away_id):
    final_min = 90
    for inc in incidents:
        if inc.get("incidentType") == "period" and inc.get("text") in ("FT", "AP", "AET"):
            t = inc.get("time", 90); at = inc.get("addedTime") or 0
            final_min = max(final_min, t + at)

    subs_out, subs_in, goals, cards, missing_next = {}, {}, [], [], []

    for inc in incidents:
        itype = inc.get("incidentType")
        is_h  = inc.get("isHome", True)
        if itype == "substitution":
            minute = inc.get("time", 90) + (inc.get("addedTime") or 0) * 0.5
            pid_out = (inc.get("playerOut") or {}).get("id")
            pid_in  = (inc.get("playerIn")  or {}).get("id")
            if pid_out: subs_out[pid_out] = min(subs_out.get(pid_out, minute), minute)
            if pid_in:  subs_in[pid_in]   = minute
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
    if not lu_data: return result
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
    print("=== scrape_octavos_results.py ===")
    tab = get_tab()
    tab.start()

    ko_data   = json.load(open(KO_PATH,    encoding="utf-8"))
    wc_data   = json.load(open(WC_RESULTS, encoding="utf-8"))
    form_data = json.load(open(FORM_PATH,  encoding="utf-8")) if FORM_PATH.exists() else {}

    # Fixtures de Octavos (en nuestro JSON están como "cuartos")
    cuartos_fixtures = ko_data.get("cuartos", [])
    if not cuartos_fixtures:
        print("ERROR: no hay fixtures en ko_data['cuartos']")
        tab.stop()
        return

    # Índice por nombres normalizados
    cuartos_index = {}
    cuartos_teams = set()
    for fx in cuartos_fixtures:
        hn = normalize_team(fx["home_name"])
        an = normalize_team(fx["away_name"])
        cuartos_index[(hn, an)] = fx
        cuartos_index[(an, hn)] = fx
        cuartos_teams.add(fx["home_name"])
        cuartos_teams.add(fx["away_name"])

    print(f"Equipos en Octavos: {sorted(cuartos_teams)}")

    # ── 1. Descubrir event IDs ────────────────────────────────────────────────
    if KO_OCTAVOS_EIDS:
        # Modo hardcoded: usar IDs ya conocidos
        discovered = {}
        for eid, meta in KO_OCTAVOS_EIDS.items():
            ev_data = api(tab, f"{BASE}/event/{eid}")
            ev = (ev_data or {}).get("event", {})
            discovered[eid] = {
                "home": meta["home"], "away": meta["away"],
                "home_id": (ev.get("homeTeam") or {}).get("id"),
                "away_id": (ev.get("awayTeam") or {}).get("id"),
                "sh": meta["sh"], "sa": meta["sa"],
                "status": "finished", "pens": meta.get("pens"),
            }
            time.sleep(0.3)
    else:
        # Modo dinámico: descubrir desde SofaScore API
        discovered = discover_octavos(tab, cuartos_teams)

    if not discovered:
        print("No se encontraron eventos de Octavos. Verificá que Chrome tenga SofaScore abierto.")
        tab.stop()
        return

    # ── 2. Filtrar terminados y matchear con bracket ──────────────────────────
    print(f"\n[2] Matcheando {len(discovered)} eventos con cuartos bracket...")
    already_done = {
        k for k, v in wc_data.get("matches", {}).items()
        if v.get("player_stats") and v.get("round_num") == ROUND_NUM
    }

    to_scrape = []
    for eid, meta in discovered.items():
        status = meta.get("status", "")
        sh = meta.get("sh"); sa = meta.get("sa")

        if str(eid) in already_done:
            print(f"  YA TIENE  eid={eid}  {meta['home']} vs {meta['away']}")
            continue

        if sh is None or sa is None:
            print(f"  SIN SCORE  eid={eid}  {meta['home']} vs {meta['away']}  status={status}")
            continue

        h_norm = normalize_team(meta["home"])
        a_norm = normalize_team(meta["away"])
        matched_fx = cuartos_index.get((h_norm, a_norm)) or cuartos_index.get((a_norm, h_norm))

        if not matched_fx:
            print(f"  SIN MATCH en bracket: {meta['home']} vs {meta['away']}")
            continue

        home_id = meta.get("home_id")
        away_id = meta.get("away_id")
        pens    = meta.get("pens")

        to_scrape.append((eid, meta["home"], meta["away"], sh, sa, home_id, away_id, pens, matched_fx))
        print(f"  OK  {meta['home']} {sh}-{sa} {meta['away']}  pens={pens}  eid={eid}")

    if not to_scrape:
        print("  Nada nuevo para scrapear.")
        tab.stop()
        return

    # ── 3. Scrape player stats ────────────────────────────────────────────────
    print(f"\n[3] Scrapeando stats de {len(to_scrape)} partidos...")
    for eid, home, away, sh, sa, home_id, away_id, pens, matched_fx in to_scrape:
        print(f"\n  [{home} {sh}-{sa} {away}]  eid={eid}")

        lu_data  = api(tab, f"{BASE}/event/{eid}/lineups")
        time.sleep(0.3)
        inc_raw  = api(tab, f"{BASE}/event/{eid}/incidents")
        time.sleep(0.3)

        incidents = (inc_raw or {}).get("incidents", [])
        final_min, subs_out, subs_in, goals, cards, missing_next = parse_incidents(
            incidents, home_id, away_id)

        player_mins = compute_player_mins(lu_data, subs_out, subs_in, final_min, home_id, away_id)
        print(f"    {len(player_mins)} jugadores candidatos  final_min={final_min}")

        player_stats = {}
        starters_counted = {True: 0, False: 0}
        for pid, pm in player_mins.items():
            d = api(tab, f"{BASE}/event/{eid}/player/{pid}/statistics")
            if not d:
                time.sleep(0.2)
                continue
            st          = d.get("statistics") or {}
            actual_mins = st.get("minutesPlayed") or 0
            if actual_mins == 0:
                continue
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
                "name": pm["name"], "mins": actual_mins, "status": player_status,
                "is_home": pm["is_home"], "team_id": pm["team_id"],
                "goals": goals_p, "assists": st.get("goalAssist") or 0,
                "yellow": st.get("yellowCards") or 0, "red": st.get("redCards") or 0,
                "rating": st.get("rating"),
                "xg": round(xg, 4), "xa": round(xa, 4),
                "saves": st.get("saves") or 0, "shots": st.get("totalShots") or 0,
                "key_passes": st.get("keyPass") or 0,
            }

            form_entry = {
                "event_id": eid, "mins": actual_mins,
                "xg": round(xg, 4), "xa": round(xa, 4),
                "goals": goals_p, "weight": WC_WEIGHT,
            }
            fd = form_data.setdefault(pid_str, {"name": pm["name"], "team": "", "matches": []})
            existing_eids = {m.get("event_id") for m in fd.get("matches", [])}
            if eid not in existing_eids:
                matches_list = [form_entry] + fd.get("matches", [])
                fd["matches"] = matches_list[:N_FORM]
                nf = form_stats(fd["matches"])
                if nf:
                    fd["form"] = nf
                fd["v2"] = True

            time.sleep(0.25 + random.random() * 0.15)

        # Determinar fecha del partido
        match_date = None
        ev_data2 = api(tab, f"{BASE}/event/{eid}")
        if ev_data2 and ev_data2.get("event"):
            match_date = ev_data2["event"].get("startTimestamp")

        wc_data.setdefault("matches", {})[str(eid)] = {
            "event_id":   eid,
            "home":       home, "away": away,
            "home_id":    home_id, "away_id": away_id,
            "group":      "KO", "round_num": ROUND_NUM,
            "timestamp":  match_date,
            "score_home": sh, "score_away": sa,
            "player_stats": player_stats,
            "incidents": {"goals": goals, "cards": cards, "missing_next": missing_next},
            "zones": {}, "team_stats": {},
        }

        # Actualizar ko_data["cuartos"] con resultado real
        matched_fx["score_home"] = sh
        matched_fx["score_away"] = sa
        matched_fx["real_event_id"] = eid
        if pens:
            matched_fx["pens_winner"] = pens

        print(f"    Guardado: {len(player_stats)} jugadores  (home={starters_counted[True]}, away={starters_counted[False]})")
        for m in missing_next:
            print(f"    SUSPENSION: {m['player_name']} ({'home' if m['is_home'] else 'away'})")

        time.sleep(0.5)

    tab.stop()

    # ── 4. Guardar JSONs ──────────────────────────────────────────────────────
    json.dump(wc_data,   open(WC_RESULTS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(form_data, open(FORM_PATH,  "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(ko_data,   open(KO_PATH,    "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nGuardado: {len(wc_data['matches'])} partidos totales, {len(form_data)} jugadores en form")

    # ── 5. Rebuild modelo DC ─────────────────────────────────────────────────
    print("\n[5] Rebuild DC model...")
    r = subprocess.run([sys.executable, str(BASE_DIR / "update_dc_with_f1.py")],
                       capture_output=True, text=True, cwd=str(BASE_DIR))
    print(r.stdout[-1000:] if r.stdout else "")
    if r.returncode != 0:
        print("ERROR update_dc:", r.stderr[-500:])

    # ── 6. Rebuild bracket ───────────────────────────────────────────────────
    print("\n[6] Rebuild bracket...")
    r = subprocess.run([sys.executable, str(BASE_DIR / "build_knockout_bracket.py")],
                       capture_output=True, text=True, cwd=str(BASE_DIR))
    print(r.stdout[-500:] if r.stdout else "")
    if r.returncode != 0:
        print("ERROR bracket:", r.stderr[-500:])

    # ── 7. Rebuild analytics ─────────────────────────────────────────────────
    print("\n[7] Rebuild analytics...")
    r = subprocess.run([sys.executable, str(BASE_DIR / "generate_wc_analytics.py")],
                       capture_output=True, text=True, cwd=str(BASE_DIR))
    print(r.stdout[-500:] if r.stdout else "")
    if r.returncode != 0:
        print("ERROR analytics:", r.stderr[-500:])

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
