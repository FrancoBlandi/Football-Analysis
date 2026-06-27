#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_knockout_bracket.py — Construye el bracket de octavos de final del WC 2026.

Bracket oficial WC 2026 (Round of 32):
  M01: 1A vs 2B  |  M09: 1B vs 2A
  M02: 1C vs 2D  |  M10: 1D vs 2C
  M03: 1E vs 2F  |  M11: 1F vs 2E
  M04: 1G vs 2H  |  M12: 1H vs 2G
  M05: 1I vs 2J  |  M13: 1J vs 2I
  M06: 1K vs 2L  |  M14: 1L vs 2K
  M07-08, M15-16: 3rd place teams (TBD)

Usa los parámetros DC del modelo para calcular lambdas.
Escribe wc2026_knockout.json con los fixtures de octavos.
"""
import json, sys, io, math
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR       = Path(__file__).parent
WC_RESULTS     = BASE_DIR / "wc2026_wc_results.json"
FIXTURES_PATH  = BASE_DIR / "wc2026_fixtures.json"
PREDICTIONS    = BASE_DIR / "wc2026_predictions.json"
KNOCKOUT_PATH  = BASE_DIR / "wc2026_knockout.json"

HOME_ADV = 1.08   # ventaja de local genérica en mundiales (neutral site)

def main():
    wc    = json.load(open(WC_RESULTS,    encoding="utf-8"))
    fix   = json.load(open(FIXTURES_PATH, encoding="utf-8"))["fixtures"]
    pred  = json.load(open(PREDICTIONS,   encoding="utf-8"))

    # ── Standings desde resultados ────────────────────────────────────────────
    standings = defaultdict(lambda: {"pts":0,"gf":0,"ga":0,"gd":0,"played":0,"team_id":None,"group":""})
    for fx in fix:
        for side, tid, tname in [("home", fx.get("home_id"), fx.get("home_name")),
                                  ("away", fx.get("away_id"), fx.get("away_name"))]:
            if tname:
                standings[tname]["team_id"] = tid
                standings[tname]["group"]   = fx.get("group","")

    for eid, md in wc["matches"].items():
        if md.get("round_num") not in (1,2,3): continue
        sh, sa = md.get("score_home"), md.get("score_away")
        if sh is None or sa is None: continue
        h, a = md["home"], md["away"]
        standings[h]["gf"] += sh; standings[h]["ga"] += sa; standings[h]["gd"] += sh-sa; standings[h]["played"] += 1
        standings[a]["gf"] += sa; standings[a]["ga"] += sh; standings[a]["gd"] += sa-sh; standings[a]["played"] += 1
        if sh > sa:  standings[h]["pts"] += 3
        elif sh==sa: standings[h]["pts"] += 1; standings[a]["pts"] += 1
        else:        standings[a]["pts"] += 3

    # Group rankings → {pos+group: team_name}
    group_teams = defaultdict(list)
    for team, s in standings.items():
        if s["group"]: group_teams[s["group"]].append((team, s))

    position = {}  # e.g. "1A" -> {team, team_id, confirmed}
    thirds   = []

    for grp in sorted(group_teams.keys()):
        ranked = sorted(group_teams[grp], key=lambda x: (-x[1]["pts"],-x[1]["gd"],-x[1]["gf"],x[0]))
        for i, (team, s) in enumerate(ranked):
            pos_key   = f"{i+1}{grp}"
            confirmed = (s["played"] == 3)
            position[pos_key] = {"team": team, "team_id": s["team_id"], "confirmed": confirmed,
                                  "pts": s["pts"], "gd": s["gd"], "gf": s["gf"]}
            if i == 2:
                thirds.append({"team": team, "team_id": s["team_id"],
                                "pts": s["pts"], "gd": s["gd"], "gf": s["gf"],
                                "group": grp, "confirmed": confirmed})

    # Best 8 third-place teams
    thirds_sorted = sorted(thirds, key=lambda x: (-x["pts"],-x["gd"],-x["gf"],x["team"]))
    qualified_thirds = thirds_sorted[:8]
    print("3ros clasificados (top 8):")
    for i, t in enumerate(thirds_sorted):
        q = "✓ CLASIFICA" if i < 8 else "eliminado"
        c = "✓" if t["confirmed"] else "(pend)"
        print(f"  {i+1}. {t['team']:<25} {t['pts']}pts GD={t['gd']:+d} GF={t['gf']} Grupo {t['group']} {c} [{q}]")

    # ── DC Parameters ─────────────────────────────────────────────────────────
    team_params = pred.get("team_params", {})
    mu     = pred.get("mu", 1.3)
    rho    = pred.get("rho", -0.1)

    def get_lam(home_name, away_name):
        hp = team_params.get(home_name, {})
        ap = team_params.get(away_name, {})
        a_h = hp.get("alpha", mu)
        b_h = hp.get("beta",  1.0)
        a_a = ap.get("alpha", mu)
        b_a = ap.get("beta",  1.0)
        lam_h = round(a_h * b_a * HOME_ADV, 4)
        lam_a = round(a_a * b_h, 4)
        return lam_h, lam_a

    def win_prob(lam_h, lam_a, max_g=8):
        p_hw = p_aw = p_d = 0
        for i in range(max_g):
            for j in range(max_g):
                p = (math.exp(-lam_h)*lam_h**i/math.factorial(i) *
                     math.exp(-lam_a)*lam_a**j/math.factorial(j))
                if i > j:   p_hw += p
                elif i < j: p_aw += p
                else:       p_d  += p
        return round(p_hw,3), round(p_d,3), round(p_aw,3)

    # ── Bracket: official WC 2026 Round of 32 ────────────────────────────────
    BRACKET = [
        # id,  home_pos, away_pos,  date
        (90000001, "1A", "2B", "2026-07-04"),
        (90000002, "1C", "2D", "2026-07-04"),
        (90000003, "1E", "2F", "2026-07-05"),
        (90000004, "1G", "2H", "2026-07-05"),
        (90000005, "1I", "2J", "2026-07-06"),
        (90000006, "1K", "2L", "2026-07-06"),
        (90000007, "1B", "2A", "2026-07-07"),
        (90000008, "1D", "2C", "2026-07-07"),
        (90000009, "1F", "2E", "2026-07-08"),
        (90000010, "1H", "2G", "2026-07-08"),
        (90000011, "1J", "2I", "2026-07-09"),
        (90000012, "1L", "2K", "2026-07-09"),
        # 3rd place matches (assigned after all groups finish)
        (90000013, "3rd_1", "3rd_2", "2026-07-10"),
        (90000014, "3rd_3", "3rd_4", "2026-07-10"),
        (90000015, "3rd_5", "3rd_6", "2026-07-11"),
        (90000016, "3rd_7", "3rd_8", "2026-07-11"),
    ]

    # Assign 3rd place teams to slots 13-16
    for i, t in enumerate(qualified_thirds[:8]):
        slot = f"3rd_{i+1}"
        position[slot] = {"team": t["team"], "team_id": t["team_id"],
                           "confirmed": t["confirmed"], "pts": t["pts"],
                           "gd": t["gd"], "gf": t["gf"]}

    # ── Build knockout fixtures ───────────────────────────────────────────────
    import time as _t
    knockout_fixtures = []

    for eid, h_pos, a_pos, date in BRACKET:
        h_data = position.get(h_pos, {})
        a_data = position.get(a_pos, {})
        h_name = h_data.get("team")
        a_name = a_data.get("team")
        h_id   = h_data.get("team_id")
        a_id   = a_data.get("team_id")

        # Timestamp (approximate)
        ts = int(_t.mktime(_t.strptime(date, "%Y-%m-%d"))) + 18*3600

        confirmed = bool(h_data.get("confirmed") and a_data.get("confirmed") and h_name and a_name)

        lam_h = lam_a = None
        p_hw = p_d = p_aw = None
        if h_name and a_name:
            lam_h, lam_a = get_lam(h_name, a_name)
            p_hw, p_d, p_aw = win_prob(lam_h, lam_a)

        fx = {
            "event_id":    eid,
            "round":       "Octavos de Final",
            "round_num":   4,
            "home_pos":    h_pos,
            "away_pos":    a_pos,
            "home_id":     h_id,
            "home_name":   h_name or "TBD",
            "away_id":     a_id,
            "away_name":   a_name or "TBD",
            "timestamp":   ts,
            "date":        date,
            "confirmed":   confirmed,
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "p_home_win":  p_hw,
            "p_draw":      p_d,
            "p_away_win":  p_aw,
        }
        knockout_fixtures.append(fx)

        status = "✓ CONFIRMADO" if confirmed else f"({h_name or h_pos} vs {a_name or a_pos})"
        if lam_h:
            print(f"  M{eid-90000000:02d}: {h_name or h_pos:<25} vs {a_name or a_pos:<25} "
                  f"λ={lam_h:.2f}/{lam_a:.2f}  {p_hw*100:.0f}%/{p_aw*100:.0f}%  {status}")
        else:
            print(f"  M{eid-90000000:02d}: {h_pos} vs {a_pos} — TBD")

    # ── Write knockout JSON ───────────────────────────────────────────────────
    out = {
        "round": "Octavos de Final",
        "fixtures": knockout_fixtures,
        "positions": position,
        "qualified_thirds": qualified_thirds,
    }
    json.dump(out, open(KNOCKOUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nEscrito: {KNOCKOUT_PATH}")
    confirmed_count = sum(1 for f in knockout_fixtures if f["confirmed"])
    print(f"Matchups confirmados: {confirmed_count}/16")


if __name__ == "__main__":
    main()
