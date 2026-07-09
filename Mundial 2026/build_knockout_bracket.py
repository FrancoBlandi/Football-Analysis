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
TEAM_STATS     = BASE_DIR / "wc2026_team_stats.json"

HOME_ADV      = 1.02   # sede neutra en mundiales (ventaja local mínima)
HOST_ADV      = 1.10   # bonus local real: juegan en estadio de su propio país
# Canada juega en Houston/Los Angeles (USA) → sin bonus de localía
HOST_TEAMS    = {"USA", "Mexico"}  # USA en Seattle, Mexico en Azteca — confirmados

# Corrección de forma WC: cuánto peso tiene el rendimiento real en el Mundial
# vs el parámetro Dixon-Coles histórico para calcular lambdas KO.
# 0.45 = 45% WC actual, 55% histórico DC.
WC_FORM_WEIGHT = 0.60
WC_ATT_CAP     = (0.72, 1.18)   # límites multiplicador de ataque
WC_DEF_CAP     = (0.65, 1.15)   # límites multiplicador de defensa
KO_EFF_DEF_FLOOR = 0.45         # piso del producto beta*def_m en get_lam: ningún equipo
                                 # es tan infranqueable que el rival espera < 0.45 goles
                                 # (evita que Spain.beta=0.238 haga λ_Belgium ≈ 0.40)

# Pesos por ronda. F3=0.25 (rotaciones, equipos clasificados) vs F2=2.0 (partido decisivo).
WC_ROUND_WEIGHTS = {1: 1.5, 2: 2.0, 3: 0.25, 4: 3.0, 5: 4.5}

# Piso del baseline histórico defensivo: ningún equipo debería tener hist_gc < 0.80
# porque eso inflata el ratio WC y hace parecer un desastre defensivo lo que es normal al WC.
WC_HIST_GC_FLOOR = 0.80

# Regresión del baseline hacia la media WC.
# Los parámetros DC extremos de equipos que jugaron vs rivales fáciles (Marruecos en AFCON,
# USA en CONCACAF) tienen alpha/beta inflados. Al comparar forma WC, el baseline justo
# es 70% propio DC + 30% media del torneo (mu para ataque, 1.0 para defensa).
# Esto corrige que Marruecos "underperformea" su alpha inflado al anotar 1 vs Brasil.
WC_BASELINE_REG = 0.30   # 30% regresión hacia media WC

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
    wc       = json.load(open(WC_RESULTS,    encoding="utf-8"))
    fix      = json.load(open(FIXTURES_PATH, encoding="utf-8"))["fixtures"]
    pred     = json.load(open(PREDICTIONS,   encoding="utf-8"))
    ts_data  = json.load(open(TEAM_STATS,    encoding="utf-8")) if TEAM_STATS.exists() else {}

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
        "best3_AEHI": "I",   # Senegal  (3ro I) → Bélgica
        "best3_CEHI": "E",   # Ecuador  (3ro E) → México
        "best3_EGIJ": "J",   # Argelia  (3ro J) → Suiza
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

    # ── Corrección de forma WC para lambdas KO ────────────────────────────────
    # Ajustada por calidad de rival + xG (luck-adjusted):
    #   att_signal = xGF / beta_rival    → luck-adjusted ataque vs defensa fuerte
    #   def_signal = xGA / alpha_rival   → luck-adjusted defensa vs ataque fuerte
    # Usa xGF/xGA de player_stats cuando está disponible; fallback a goles reales.
    # xG resuelve: Marruecos concedió 1 a Holanda con solo 0.24 xGA → mala suerte,
    #              su defensa real fue excelente. Canada vs Qatar: xGF=4.91 vs 6 goles.
    # Baseline de comparación: propio alpha/beta DC.

    # Paso 1: extraer xGF/xGA por equipo por partido desde player_stats.
    # Normalizar a 90 min para partidos con alargue (max_mins=120 → scale=0.75).
    _match_xga: dict  = {}   # eid → {team: xga_90min}
    _match_norm: dict = {}   # eid → scale (90/actual_mins)
    for _eid, _md in wc.get("matches", {}).items():
        _ps = _md.get("player_stats") or {}
        if not _ps: continue
        _home = _md.get("home"); _away = _md.get("away")
        if not _home or not _away: continue
        _max_m = max((p.get("mins") or 0) for p in _ps.values())
        _scale = 90 / _max_m if _max_m > 90 else 1.0   # alargue → normalizar a 90min
        _match_norm[_eid] = _scale
        _xg_h = sum((p.get("xg") or 0) for p in _ps.values() if p.get("is_home") is True) * _scale
        _xg_a = sum((p.get("xg") or 0) for p in _ps.values() if p.get("is_home") is False) * _scale
        _match_xga[_eid] = {_home: _xg_a, _away: _xg_h}   # xGA del home = xGF del away

    _wc_gf_w: dict = {}; _wc_gc_w: dict = {}; _wc_rw: dict = {}
    for _eid, _md in wc.get("matches", {}).items():
        _rn = _md.get("round_num")
        if _rn not in WC_ROUND_WEIGHTS: continue
        _sh = _md.get("score_home"); _sa = _md.get("score_away")
        if _sh is None or _sa is None: continue
        _w     = WC_ROUND_WEIGHTS[_rn]
        _home  = _md["home"]; _away = _md["away"]
        _h_p   = team_params.get(_home, {}); _a_p = team_params.get(_away, {})
        _h_alp = _h_p.get("alpha", mu);  _h_bet = _h_p.get("beta", 1.0)
        _a_alp = _a_p.get("alpha", mu);  _a_bet = _a_p.get("beta", 1.0)
        # Ataque: goles reales normalizados a 90min (partidos con alargue se escalan
        #         para no inflar la señal por 30 min extra de juego).
        # Defensa: xGA solo en partidos KO (round_num >= 4) ya normalizados a 90min.
        #          En grupos la muestra de 3 partidos promedia la suerte.
        # KO xGA: Marruecos-Holanda (0.18 xGA/90, concedió 0.75 → gran defensa)
        #         Bélgica-Senegal (2.79 xGA/90, concedió 2.25 → tuvo suerte)
        _norm = _match_norm.get(_eid, 1.0)
        _sh_n = _sh * _norm   # goles home normalizados a 90min
        _sa_n = _sa * _norm   # goles away normalizados a 90min
        if _rn >= 4:
            _xga  = _match_xga.get(_eid, {})
            _h_gc = _xga.get(_home, _sa_n)  # xGA ya normalizado; fallback a goles norm.
            _a_gc = _xga.get(_away, _sh_n)
        else:
            _h_gc = _sa_n   # grupos: goles reales normalizados
            _a_gc = _sh_n
        # Home team: goles normalizados vs beta_rival; (x)GA de alpha_rival
        _wc_gf_w[_home] = _wc_gf_w.get(_home, 0.0) + (_sh_n / _a_bet) * _w
        _wc_gc_w[_home] = _wc_gc_w.get(_home, 0.0) + (_h_gc / _a_alp) * _w
        _wc_rw[_home]   = _wc_rw.get(_home, 0.0)   + _w
        # Away team: goles normalizados vs beta_rival; (x)GA de alpha_rival
        _wc_gf_w[_away] = _wc_gf_w.get(_away, 0.0) + (_sa_n / _h_bet) * _w
        _wc_gc_w[_away] = _wc_gc_w.get(_away, 0.0) + (_a_gc / _h_alp) * _w
        _wc_rw[_away]   = _wc_rw.get(_away, 0.0)   + _w

    # Dificultad de calendario WC por equipo: promedio ponderado del alpha DC de sus rivales.
    # Equipos que enfrentaron rivales más fuertes → señal WC más confiable → mayor peso.
    # Equipos que jugaron contra Qatar/SA → señal menos confiable → menor peso.
    _sched: dict = {}
    for _eid, _md in wc.get("matches", {}).items():
        _rn = _md.get("round_num")
        if _rn not in WC_ROUND_WEIGHTS: continue
        _w = WC_ROUND_WEIGHTS[_rn]
        _h, _a = _md["home"], _md["away"]
        _ha = team_params.get(_h, {}).get("alpha", mu)
        _aa = team_params.get(_a, {}).get("alpha", mu)
        _sched[_h] = _sched.get(_h, 0.0) + _aa * _w
        _sched[_a] = _sched.get(_a, 0.0) + _ha * _w
    # Normalizar por total_weight por equipo y calcular promedio global
    _sched_pg = {_t: _sched[_t] / _wc_rw[_t] for _t in _sched if _wc_rw.get(_t, 0) > 0}
    _global_ss = sum(_sched_pg.values()) / len(_sched_pg) if _sched_pg else 1.0

    def _eff_wc_weight(team):
        ss = _sched_pg.get(team, _global_ss)
        w  = WC_FORM_WEIGHT * (ss / _global_ss)
        return max(0.25, min(0.75, w))   # bounds: nunca menos de 25% ni más de 75%

    _wc_form: dict = {}   # team → (att_mult, def_mult)
    for _t, _rw in _wc_rw.items():
        if _rw == 0: continue
        _tp       = team_params.get(_t, {})
        _own_alp  = _tp.get("alpha", mu)
        _own_bet  = _tp.get("beta",  1.0)
        _wc_gf_pg = _wc_gf_w[_t] / _rw
        _wc_gc_pg = _wc_gc_w[_t] / _rw
        _att_ratio = _wc_gf_pg / _own_alp
        _def_ratio = _wc_gc_pg / _own_bet
        _fw = _eff_wc_weight(_t)   # peso ajustado por dificultad de calendario
        _att_m = max(WC_ATT_CAP[0], min(WC_ATT_CAP[1], (1 - _fw) + _fw * _att_ratio))
        _def_m = max(WC_DEF_CAP[0], min(WC_DEF_CAP[1], (1 - _fw) + _fw * _def_ratio))
        _wc_form[_t] = (_att_m, _def_m)

    def _form(team):
        return _wc_form.get(team, (1.0, 1.0))

    def get_lam(home_name, away_name):
        hp = team_params.get(home_name, {})
        ap = team_params.get(away_name, {})
        h_att, h_def = _form(home_name)
        a_att, a_def = _form(away_name)
        # Co-sede en su propio estadio → HOST_ADV.
        # Canada juega en Houston/LA (USA) → sede neutra real = 1.0 (no HOME_ADV).
        # Otros partidos KO en sedes neutras → HOME_ADV mínimo (1.02).
        if home_name in HOST_TEAMS:
            local_mult = HOST_ADV
        elif home_name == "Canada":
            local_mult = 1.0   # juega en USA, no hay ventaja de local
        else:
            local_mult = HOME_ADV
        # alpha ajustado por forma atacante; beta del rival ajustado por forma defensiva.
        # Piso en el producto efectivo de defensa (beta * def_m): evita que DC betas
        # extremadamente bajos (ej. Spain 0.238) hagan al rival casi imposible de anotar.
        eff_h_def = max(KO_EFF_DEF_FLOOR, hp.get("beta", 1.0) * h_def)
        eff_a_def = max(KO_EFF_DEF_FLOOR, ap.get("beta", 1.0) * a_def)
        lam_h = round(hp.get("alpha", mu) * h_att * eff_a_def * local_mult, 4)
        lam_a = round(ap.get("alpha", mu) * a_att * eff_h_def, 4)
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

    # ── Build Cuartos de Final (R16) bracket ──────────────────────────────────
    # Determinar ganadores de cada R32 match para proyectar R16
    wc_matches = wc.get("matches", {})
    r32_winners: dict[int, dict] = {}  # eid → {team, team_id, confirmed}

    # Leer resultados de partidos ya jugados (player_stats implica que se jugó)
    played_map: dict = {}  # eid → {home, home_id, away, away_id, sh, sa, pens_winner}
    for eid_str, md in wc_matches.items():
        if md.get("round_num") == 4 and md.get("score_home") is not None:
            played_map[md["event_id"]] = md

    for fx in knockout_fixtures:
        eid    = fx["event_id"]
        h_name = fx["home_name"]; h_id = fx["home_id"]
        a_name = fx["away_name"]; a_id = fx["away_id"]
        ph     = fx.get("p_home_win", 0.5) or 0.5
        pa     = fx.get("p_away_win", 0.25) or 0.25

        # Buscar por eid en wc_matches (los EIDs reales, no los sintéticos 9000000x)
        # Los eids en wc_matches tienen el eid real de SofaScore
        actual_md = None
        for eid_str, md in wc_matches.items():
            if md.get("round_num") == 4:
                if ((md.get("home") == h_name or md.get("away") == h_name) and
                    (md.get("home") == a_name or md.get("away") == a_name)):
                    actual_md = md
                    break

        if actual_md:
            sh = actual_md.get("score_home", 0); sa = actual_md.get("score_away", 0)
            pens = actual_md.get("pens_winner")
            if pens == "home" or (sh > sa and not pens):
                winner_name = actual_md["home"]; winner_id = actual_md.get("home_id")
            elif pens == "away" or (sa > sh and not pens):
                winner_name = actual_md["away"]; winner_id = actual_md.get("away_id")
            else:
                winner_name = h_name; winner_id = h_id  # fallback home
            r32_winners[eid] = {"team": winner_name, "team_id": winner_id, "confirmed": True}
        elif h_name != "TBD" and a_name != "TBD":
            # Proyección: ganador más probable por modelo
            if ph >= pa:
                winner_name = h_name; winner_id = h_id
            else:
                winner_name = a_name; winner_id = a_id
            r32_winners[eid] = {"team": winner_name, "team_id": winner_id, "confirmed": False}

    # Bracket R16 (Cuartos): M(2k-1) winner vs M(2k) winner
    R16_BRACKET = [
        (90000101, 90000001, 90000002, "2026-07-14"),  # C01: M01w vs M02w
        (90000102, 90000003, 90000004, "2026-07-14"),  # C02: M03w vs M04w
        (90000103, 90000005, 90000006, "2026-07-15"),  # C03: M05w vs M06w
        (90000104, 90000007, 90000008, "2026-07-15"),  # C04: M07w vs M08w
        (90000105, 90000009, 90000010, "2026-07-16"),  # C05: M09w vs M10w
        (90000106, 90000011, 90000012, "2026-07-16"),  # C06: M11w vs M12w
        (90000107, 90000013, 90000014, "2026-07-17"),  # C07: M13w vs M14w
        (90000108, 90000015, 90000016, "2026-07-17"),  # C08: M15w vs M16w
    ]

    cuartos_fixtures = []
    print("\nBracket Cuartos de Final (proyectado):")
    for c_eid, m_h, m_a, date in R16_BRACKET:
        hw = r32_winners.get(m_h, {})
        aw = r32_winners.get(m_a, {})
        h_name = hw.get("team", "TBD"); h_id = hw.get("team_id")
        a_name = aw.get("team", "TBD"); a_id = aw.get("team_id")
        confirmed = hw.get("confirmed", False) and aw.get("confirmed", False)

        ts = int(_t.mktime(_t.strptime(date, "%Y-%m-%d"))) + 18*3600
        lam_h = lam_a = p_hw = p_d = p_aw = None
        if h_name != "TBD" and a_name != "TBD":
            lam_h, lam_a = get_lam(h_name, a_name)
            p_hw, p_d, p_aw = win_prob(lam_h, lam_a)

        c_num = c_eid - 90000100
        conf_tag = "✓" if confirmed else "~"
        if lam_h:
            print(f"  C{c_num:02d}: {h_name:<26} vs {a_name:<26} "
                  f"λ={lam_h:.2f}/{lam_a:.2f}  {p_hw*100:.0f}%D{p_d*100:.0f}%/{p_aw*100:.0f}%  {conf_tag}")
        else:
            print(f"  C{c_num:02d}: {'TBD':<26} vs {'TBD':<26} — pendiente R32")

        cuartos_fixtures.append({
            "event_id":    c_eid,
            "round":       "Cuartos de Final",
            "round_num":   5,
            "home_id":     h_id,
            "home_name":   h_name,
            "away_id":     a_id,
            "away_name":   a_name,
            "timestamp":   ts,
            "date":        date,
            "confirmed":   confirmed,
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "p_home_win":  p_hw,
            "p_draw":      p_d,
            "p_away_win":  p_aw,
            "r32_home_eid": m_h,
            "r32_away_eid": m_a,
        })

    # ── Build Cuartos de Final (QF) bracket from Octavos winners ─────────────
    # Leer resultados de Octavos (round_num=5) desde wc_results
    r16_winners: dict[int, dict] = {}  # c_eid → {team, team_id, confirmed}

    for fx in cuartos_fixtures:
        c_eid  = fx["event_id"]
        h_name = fx["home_name"]; h_id = fx.get("home_id")
        a_name = fx["away_name"]; a_id = fx.get("away_id")
        ph     = fx.get("p_home_win", 0.5) or 0.5
        pa     = fx.get("p_away_win", 0.25) or 0.25

        # Buscar resultado real en wc_matches (round_num=5)
        actual_md = None
        for eid_str, md in wc_matches.items():
            if md.get("round_num") == 5:
                if ((md.get("home") == h_name or md.get("away") == h_name) and
                    (md.get("home") == a_name or md.get("away") == a_name)):
                    actual_md = md
                    break

        if actual_md and actual_md.get("score_home") is not None:
            sh = actual_md["score_home"]; sa = actual_md["score_away"]
            pens = actual_md.get("pens_winner") or fx.get("pens_winner")
            if pens == "home" or (sh > sa and not pens):
                winner_name = actual_md["home"]; winner_id = actual_md.get("home_id")
            elif pens == "away" or (sa > sh and not pens):
                winner_name = actual_md["away"]; winner_id = actual_md.get("away_id")
            else:
                winner_name = h_name; winner_id = h_id
            r16_winners[c_eid] = {"team": winner_name, "team_id": winner_id, "confirmed": True}
            # Pegar score real en cuartos_fixture
            fx["score_home"] = sh; fx["score_away"] = sa
            if pens: fx["pens_winner"] = pens
        elif h_name != "TBD" and a_name != "TBD":
            # Proyección: ganador más probable
            if ph >= pa:
                winner_name = h_name; winner_id = h_id
            else:
                winner_name = a_name; winner_id = a_id
            r16_winners[c_eid] = {"team": winner_name, "team_id": winner_id, "confirmed": False}

    # Bracket QF: C01w vs C02w, C03w vs C04w, C05w vs C06w, C07w vs C08w
    QF_BRACKET = [
        (90000201, 90000101, 90000102, "2026-07-18"),  # QF1: C01w vs C02w
        (90000202, 90000103, 90000104, "2026-07-18"),  # QF2: C03w vs C04w
        (90000203, 90000105, 90000106, "2026-07-19"),  # QF3: C05w vs C06w
        (90000204, 90000107, 90000108, "2026-07-19"),  # QF4: C07w vs C08w
    ]

    semifinales_fixtures = []
    print("\nBracket Cuartos de Final / QF (proyectado):")
    for qf_eid, c_h, c_a, date in QF_BRACKET:
        hw = r16_winners.get(c_h, {})
        aw = r16_winners.get(c_a, {})
        h_name = hw.get("team", "TBD"); h_id = hw.get("team_id")
        a_name = aw.get("team", "TBD"); a_id = aw.get("team_id")
        confirmed = hw.get("confirmed", False) and aw.get("confirmed", False)

        ts = int(_t.mktime(_t.strptime(date, "%Y-%m-%d"))) + 18*3600
        lam_h = lam_a = p_hw = p_d = p_aw = None
        if h_name != "TBD" and a_name != "TBD":
            lam_h, lam_a = get_lam(h_name, a_name)
            p_hw, p_d, p_aw = win_prob(lam_h, lam_a)

        qf_num = qf_eid - 90000200
        conf_tag = "✓" if confirmed else "~"
        if lam_h:
            print(f"  QF{qf_num}: {h_name:<26} vs {a_name:<26} "
                  f"λ={lam_h:.2f}/{lam_a:.2f}  {p_hw*100:.0f}%D{p_d*100:.0f}%/{p_aw*100:.0f}%  {conf_tag}")
        else:
            print(f"  QF{qf_num}: {'TBD':<26} vs {'TBD':<26} — pendiente Octavos")

        semifinales_fixtures.append({
            "event_id":    qf_eid,
            "round":       "Cuartos de Final",
            "round_num":   6,
            "home_id":     h_id,
            "home_name":   h_name,
            "away_id":     a_id,
            "away_name":   a_name,
            "timestamp":   ts,
            "date":        date,
            "confirmed":   confirmed,
            "lambda_home": lam_h,
            "lambda_away": lam_a,
            "p_home_win":  p_hw,
            "p_draw":      p_d,
            "p_away_win":  p_aw,
            "r16_home_eid": c_h,
            "r16_away_eid": c_a,
        })

    # ── Write knockout JSON ───────────────────────────────────────────────────
    out = {
        "round": "Octavos de Final",
        "fixtures": knockout_fixtures,
        "cuartos":  cuartos_fixtures,
        "semifinales": semifinales_fixtures,
        "positions": position,
        "thirds_pool": {grp: t for grp, t in pool_thirds.items()},
    }
    json.dump(out, open(KNOCKOUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    confirmed_count = sum(1 for f in knockout_fixtures if f["confirmed"])
    cuartos_conf    = sum(1 for f in cuartos_fixtures  if f["confirmed"])
    semis_conf      = sum(1 for f in semifinales_fixtures if f["confirmed"])
    print(f"\nEscrito: {KNOCKOUT_PATH}  ({confirmed_count}/16 octavos, {cuartos_conf}/8 cuartos, {semis_conf}/4 QF confirmados)")


if __name__ == "__main__":
    main()
