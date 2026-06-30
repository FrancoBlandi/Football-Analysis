#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_knockout_bracket.py — Bracket oficial de 16avos del WC 2026.

Bracket oficial (fuente: imagen FIFA/SofaScore):
  M01: 1E  vs 3D           Germany vs Paraguay
  M02: 1I  vs 3F           France  vs Sweden
  M03: 2A  vs 2B           South Africa vs Canada
  M04: 1F  vs 2C           Netherlands vs Morocco
  M05: 2K  vs 2L           Portugal vs Ghana (TBD)
  M06: 1H  vs 2J           Spain vs Austria (TBD)
  M07: 1D  vs 3B           USA vs Bosnia & Herzegovina
  M08: 1G  vs 3rd(AEHIJ)  Belgium vs mejor 3ro de A/E/H/I/J
  M09: 1C  vs 2F           Brazil vs Japan
  M10: 2E  vs 2I           Côte d'Ivoire vs Norway
  M11: 1A  vs 3rd(CEHI)   Mexico vs mejor 3ro de C/E/H/I
  M12: 1L  vs 3rd(EHIJK)  England vs mejor 3ro de E/H/I/J/K (TBD)
  M13: 1J  vs 2H           Argentina vs Cabo Verde (CONFIRMADO)
  M14: 2D  vs 2G           Australia vs Egypt
  M15: 1B  vs 3rd(EGIJ)   Switzerland vs mejor 3ro de E/G/I/J
  M16: 1K  vs 3rd(IJL)    Colombia vs mejor 3ro de I/J/L (TBD)
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

HOME_ADV = 1.02   # sede neutra en mundiales (ventaja local mínima)

# Bracket oficial WC 2026 — (eid, home_pos, away_pos, fecha, descripcion)
# Las posiciones 3rd_AEHI etc. se resuelven dinámicamente según standings
BRACKET = [
    (90000001, "1E",        "3D",         "2026-07-04", "Germany vs Paraguay"),
    (90000002, "1I",        "3F",         "2026-07-04", "France vs Sweden"),
    (90000003, "2A",        "2B",         "2026-07-05", "South Africa vs Canada"),
    (90000004, "1F",        "2C",         "2026-07-05", "Netherlands vs Morocco"),
    (90000005, "2K",        "2L",         "2026-07-06", "2K vs 2L"),
    (90000006, "1H",        "2J",         "2026-07-06", "Spain vs 2J"),
    (90000007, "1D",        "3B",         "2026-07-07", "USA vs Bosnia"),
    (90000008, "1G",        "best3_AEHI", "2026-07-07", "Belgium vs 3ro AEHIJ"),
    (90000009, "1C",        "2F",         "2026-07-08", "Brazil vs Japan"),
    (90000010, "2E",        "2I",         "2026-07-08", "CIV vs Norway"),
    (90000011, "1A",        "best3_CEHI", "2026-07-09", "Mexico vs 3ro CEHI"),
    (90000012, "1L",        "best3_EHIJ", "2026-07-09", "1L vs 3ro EHIJK"),
    (90000013, "1J",        "2H",         "2026-07-10", "Argentina vs Cabo Verde"),
    (90000014, "2D",        "2G",         "2026-07-10", "Australia vs Egypt"),
    (90000015, "1B",        "best3_EGIJ", "2026-07-11", "Switzerland vs 3ro EGIJ"),
    (90000016, "1K",        "best3_IJL",  "2026-07-11", "1K vs 3ro IJL"),
]

# 3ros con posición fija en el bracket (no van al pool de "mejores 3ros")
FIXED_THIRDS = {"B", "D", "F"}

# Matchups confirmados oficialmente aunque el grupo no haya terminado
CONFIRMED_MATCH_OVERRIDES = {
    90000013,   # Argentina vs Cabo Verde — confirmado por FIFA aunque J no terminó
}


def main():
    wc    = json.load(open(WC_RESULTS,    encoding="utf-8"))
    fix   = json.load(open(FIXTURES_PATH, encoding="utf-8"))["fixtures"]
    pred  = json.load(open(PREDICTIONS,   encoding="utf-8"))

    # ── Standings ─────────────────────────────────────────────────────────────
    standings = defaultdict(lambda: {"pts":0,"gf":0,"ga":0,"gd":0,"played":0,"team_id":None,"group":""})
    for fx in fix:
        for tid, tname in [(fx.get("home_id"), fx.get("home_name")),
                            (fx.get("away_id"), fx.get("away_name"))]:
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

    # Rankings por grupo
    group_teams = defaultdict(list)
    for team, s in standings.items():
        if s["group"]: group_teams[s["group"]].append((team, s))

    # position["1A"], position["2B"], position["3C"], etc.
    position = {}
    thirds_by_group = {}   # group → {team, pts, gd, gf, confirmed, team_id}

    for grp in sorted(group_teams.keys()):
        ranked = sorted(group_teams[grp], key=lambda x: (-x[1]["pts"],-x[1]["gd"],-x[1]["gf"],x[0]))
        for i, (team, s) in enumerate(ranked):
            confirmed = (s["played"] == 3)
            pos_key   = f"{i+1}{grp}"
            position[pos_key] = {"team": team, "team_id": s["team_id"],
                                   "confirmed": confirmed,
                                   "pts": s["pts"], "gd": s["gd"], "gf": s["gf"]}
            if i == 2:
                thirds_by_group[grp] = {"team": team, "team_id": s["team_id"],
                                         "pts": s["pts"], "gd": s["gd"], "gf": s["gf"],
                                         "group": grp, "confirmed": confirmed}

    # ── 3ros fijos ya en el bracket (B=Bosnia, D=Paraguay, F=Sweden) ──────────
    for grp in FIXED_THIRDS:
        t = thirds_by_group.get(grp, {})
        pos_key = f"3{grp}"
        if pos_key not in position and t:
            position[pos_key] = {"team": t["team"], "team_id": t["team_id"],
                                   "confirmed": t.get("confirmed", False),
                                   "pts": t["pts"], "gd": t["gd"], "gf": t["gf"]}

    # ── Pool de mejores 3ros (excl. B, D, F que ya tienen posición fija) ──────
    pool_thirds = {
        grp: t for grp, t in thirds_by_group.items()
        if grp not in FIXED_THIRDS
    }
    # Ordenar por pts, gd, gf
    pool_sorted = sorted(pool_thirds.items(),
                         key=lambda x: (-x[1]["pts"],-x[1]["gd"],-x[1]["gf"],x[0]))
    print("Pool de mejores 3ros (excluyendo B/D/F):")
    for grp, t in pool_sorted:
        c = "✓" if t["confirmed"] else "(pend)"
        print(f"  3{grp}: {t['team']:<25} {t['pts']}pts GD={t['gd']:+d} GF={t['gf']} {c}")

    # Asignación de 3ros a slots del bracket
    # Reglas de slots (grupos que pueden llenar cada slot):
    SLOT_GROUPS = {
        "best3_AEHI": list("AEHIJ"),
        "best3_CEHI": list("CEHI"),   # F ya fijo
        "best3_EHIJ": list("EHIJK"),
        "best3_EGIJ": list("EGIJ"),   # F ya fijo
        "best3_IJL":  list("IJL"),    # D ya fijo
    }
    SLOT_ORDER = ["best3_AEHI", "best3_CEHI", "best3_EHIJ", "best3_EGIJ", "best3_IJL"]

    # Asignación oficial FIFA confirmada (override del algoritmo greedy)
    CONFIRMED_SLOT_GROUPS = {
        "best3_CEHI": "E",   # Ecuador (3ro E) → Mexico (slot CEHI) — bracket oficial FIFA
    }

    # Greedy: asignar el mejor 3ro disponible a cada slot que lo acepte
    used_groups = set()
    slot_assigned = {}

    # Aplicar overrides confirmados primero
    for slot, grp in CONFIRMED_SLOT_GROUPS.items():
        if grp in pool_thirds:
            t = pool_thirds[grp]
            slot_assigned[slot] = (grp, t)
            used_groups.add(grp)
            position[slot] = {"team": t["team"], "team_id": t["team_id"],
                               "confirmed": t["confirmed"],
                               "pts": t["pts"], "gd": t["gd"], "gf": t["gf"]}
            print(f"  {slot} → 3{grp}: {t['team']} [CONFIRMADO FIFA]")

    # Primero asignar los que solo tienen UNA posibilidad de grupo (más restrictivos)
    # Calcular cuántos slots puede llenar cada grupo
    group_slot_count = defaultdict(list)
    for slot, grps in SLOT_GROUPS.items():
        for grp in grps:
            if grp in pool_thirds:
                group_slot_count[grp].append(slot)

    # Iterar slots en orden; para cada slot, asignar el mejor 3ro disponible del grupo correcto
    for slot in SLOT_ORDER:
        if slot in slot_assigned:
            continue   # ya asignado por override confirmado
        candidates = [
            (grp, pool_thirds[grp]) for grp in SLOT_GROUPS[slot]
            if grp in pool_thirds and grp not in used_groups
        ]
        if not candidates:
            slot_assigned[slot] = None
            continue
        # El mejor candidato (mayor pts → gd → gf)
        best_grp, best_t = sorted(candidates,
                                   key=lambda x: (-x[1]["pts"],-x[1]["gd"],-x[1]["gf"],x[0]))[0]
        slot_assigned[slot] = (best_grp, best_t)
        used_groups.add(best_grp)
        position[slot] = {"team": best_t["team"], "team_id": best_t["team_id"],
                           "confirmed": best_t["confirmed"],
                           "pts": best_t["pts"], "gd": best_t["gd"], "gf": best_t["gf"]}
        print(f"  {slot} → 3{best_grp}: {best_t['team']} {'✓' if best_t['confirmed'] else '(pend)'}")

    # ── DC Parameters ─────────────────────────────────────────────────────────
    team_params = pred.get("team_params", {})
    mu = pred.get("mu", 1.3)

    def get_lam(home_name, away_name):
        hp = team_params.get(home_name, {})
        ap = team_params.get(away_name, {})
        lam_h = round(hp.get("alpha", mu) * ap.get("beta", 1.0) * HOME_ADV, 4)
        lam_a = round(ap.get("alpha", mu) * hp.get("beta", 1.0), 4)
        return lam_h, lam_a

    def win_prob(lam_h, lam_a, max_g=8):
        p_hw = p_aw = p_d = 0
        for i in range(max_g):
            for j in range(max_g):
                p = (math.exp(-lam_h)*lam_h**i/math.factorial(i) *
                     math.exp(-lam_a)*lam_a**j/math.factorial(j))
                if i > j:   p_hw += p
                elif i < j: p_aw += p
                else:        p_d  += p
        return round(p_hw,3), round(p_d,3), round(p_aw,3)

    # ── Build knockout fixtures ───────────────────────────────────────────────
    import time as _t
    knockout_fixtures = []
    print("\nBracket 16avos de Final:")

    for eid, h_pos, a_pos, date, desc in BRACKET:
        h_data = position.get(h_pos, {})
        a_data = position.get(a_pos, {})
        h_name = h_data.get("team")
        a_name = a_data.get("team")
        h_id   = h_data.get("team_id")
        a_id   = a_data.get("team_id")
        ts     = int(_t.mktime(_t.strptime(date, "%Y-%m-%d"))) + 18*3600

        confirmed = bool(h_name and a_name and
                        (eid in CONFIRMED_MATCH_OVERRIDES or
                         (h_data.get("confirmed") and a_data.get("confirmed"))))

        lam_h = lam_a = p_hw = p_d = p_aw = None
        if h_name and a_name:
            lam_h, lam_a = get_lam(h_name, a_name)
            p_hw, p_d, p_aw = win_prob(lam_h, lam_a)

        fx = {
            "event_id":    eid,
            "round":       "Octavos de Final",
            "round_num":   4,
            "home_pos":    h_pos,
            "away_pos":    a_pos,
            "desc":        desc,
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

        m_num = eid - 90000000
        h_show = h_name or h_pos
        a_show = a_name or a_pos
        if lam_h:
            status = "✓" if confirmed else "~"
            print(f"  M{m_num:02d}: {h_show:<26} vs {a_show:<26} "
                  f"λ={lam_h:.2f}/{lam_a:.2f}  {p_hw*100:.0f}%D{p_d*100:.0f}%/{p_aw*100:.0f}%  {status}")
        else:
            print(f"  M{m_num:02d}: {h_pos:<26} vs {a_pos:<26} — TBD")

    # ── Write knockout JSON ───────────────────────────────────────────────────
    out = {
        "round": "Octavos de Final",
        "fixtures": knockout_fixtures,
        "positions": position,
        "thirds_pool": {grp: t for grp, t in pool_thirds.items()},
    }
    json.dump(out, open(KNOCKOUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    confirmed_count = sum(1 for f in knockout_fixtures if f["confirmed"])
    print(f"\nEscrito: {KNOCKOUT_PATH}  ({confirmed_count}/16 confirmados)")


if __name__ == "__main__":
    main()
