#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infer_wide_players.py — Detecta automáticamente mediocampistas (pos=M) que juegan
por afuera basándose en sus cruces (totalCross) en los partidos del Mundial.

Usa el endpoint /event/{eid}/lineups que ya incluye estadísticas inline por jugador,
incluyendo totalCross — el indicador más confiable de juego por banda.

Umbral: promedio >= 1.5 cruces/partido → candidato a wide_mid.
Escribe los PIDs a agregar en PLAYER_TYPE_OVERRIDES en generate_wc_analytics.py.
"""
import pychrome, json, time, sys, io
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = Path(__file__).parent
WC_RESULTS = BASE_DIR / "wc2026_wc_results.json"
OUT_PATH   = BASE_DIR / "wide_players_detected.json"

CDP_PORT  = "http://localhost:9222"
BASE_URL  = "https://www.sofascore.com/api/v1"

CROSS_THRESHOLD   = 2.0   # avg crosses/partido (umbral base)
CROSS_SHOT_RATIO  = 2.0   # cruces deben ser > remates * 2 (filtra set-piece centrales)
MAX_SHOTS         = 1.5   # un volante wide no remata más de 1.5 veces/PJ en promedio
MIN_MATCHES       = 1     # mínimo de partidos con datos para incluir
POS_TARGET        = {"M"}  # solo mediocampistas (M = posición FM)


def get_tab():
    browser = pychrome.Browser(url=CDP_PORT)
    for t in browser.list_tab():
        url = t._kwargs.get("url", "")
        if "sofascore.com" in url and "sync" not in url and "pixel" not in url:
            return t
    raise RuntimeError("No SofaScore tab found")


def api(tab, url, retries=2):
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
        time.sleep(1)
    return None


def main():
    tab = get_tab()
    tab.start()

    wc = json.load(open(WC_RESULTS, encoding="utf-8"))

    # pid → {name, national_team, crosses: [list], pos: str}
    player_data = defaultdict(lambda: {
        "name": "", "national_team": "", "pos": None, "crosses": [], "shots": [], "matches": 0
    })

    eids_processed = 0
    for eid_str, md in wc["matches"].items():
        if md.get("round_num") not in (1, 2, 3):
            continue
        if md.get("score_home") is None:
            continue

        eid = int(eid_str)
        home, away = md["home"], md["away"]

        lu = api(tab, f"{BASE_URL}/event/{eid}/lineups")
        if not lu:
            print(f"  [{eid}] sin lineup")
            time.sleep(0.3)
            continue

        for side_key in ("home", "away"):
            nat_team = home if side_key == "home" else away
            side     = lu.get(side_key, {})
            for p in (side.get("players") or []):
                pl   = p.get("player", {})
                pid  = pl.get("id")
                name = pl.get("name", "")
                pos  = p.get("position", "")   # G/D/M/F según FM/SofaScore
                if not pid or pos not in POS_TARGET:
                    continue
                st      = p.get("statistics", {})
                crosses = st.get("totalCross") or 0
                shots   = st.get("totalShots") or 0
                mins    = st.get("minutesPlayed") or 0
                if mins < 30:
                    continue   # ignorar participaciones muy cortas

                pd = player_data[pid]
                pd["name"]          = name
                pd["national_team"] = nat_team
                pd["pos"]           = pos
                pd["crosses"].append(crosses)
                pd["shots"].append(shots)
                pd["matches"]       += 1

        eids_processed += 1
        print(f"  [{eid}] {home} vs {away} OK  ({eids_processed} processed)")
        time.sleep(0.4)

    tab.stop()

    # Calcular promedio y filtrar
    print(f"\n{'='*60}")
    print(f"Mediocampistas con avg crosses ≥ {CROSS_THRESHOLD}/partido (min {MIN_MATCHES} PJ):")
    print(f"{'='*60}")
    candidates = []
    for pid, pd in player_data.items():
        if pd["matches"] < MIN_MATCHES:
            continue
        avg_crosses = sum(pd["crosses"]) / len(pd["crosses"])
        avg_shots   = sum(pd["shots"])   / len(pd["shots"]) if pd["shots"] else 0
        # Filtro triple: cruces suficientes + cruces >> remates + cap absoluto de remates
        # El cap de remates excluye set-piece takers centrales (Rice, Fernandes, Sabitzer)
        # que cruzan mucho pero también rematan — algo que un extremo puro no hace.
        if (avg_crosses >= CROSS_THRESHOLD
                and avg_crosses > avg_shots * CROSS_SHOT_RATIO
                and avg_shots <= MAX_SHOTS):
            candidates.append((pid, pd["name"], pd["national_team"], avg_crosses, avg_shots, pd["matches"]))

    candidates.sort(key=lambda x: -x[3])
    for pid, name, team, avg, avg_sh, n in candidates:
        ratio = avg / max(avg_sh, 0.1)
        print(f"  pid={pid:<10} {name:<28} ({team:<20}) cruces={avg:.1f}  remates={avg_sh:.1f}  ratio={ratio:.1f}  {n}PJ")

    # Guardar resultado
    out = {
        "threshold": CROSS_THRESHOLD,
        "cross_shot_ratio": CROSS_SHOT_RATIO,
        "wide_mid_candidates": [
            {"pid": pid, "name": name, "team": team,
             "avg_crosses": round(avg, 2), "avg_shots": round(avg_sh, 2), "matches": n}
            for pid, name, team, avg, avg_sh, n in candidates
        ]
    }
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n{len(candidates)} candidatos. Guardado: {OUT_PATH}")
    print("\nAgregar en PLAYER_TYPE_OVERRIDES de generate_wc_analytics.py:")
    for pid, name, team, avg, avg_sh, n in candidates:
        print(f'    {pid}: "wide_mid",   # {name} ({team}) cruces={avg:.1f} rem={avg_sh:.1f}')


if __name__ == "__main__":
    main()
