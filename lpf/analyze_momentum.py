#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_momentum.py — Análisis de momentum intra-partido LPF 2026.

Genera lpf/momentum_report.html con:
  1. ¿Existe el momentum? (autocorrelación, distribución)
  2. Perfil temporal del partido
  3. Triggers: impacto de eventos (goles, rojas, subs)
  4. Duración del efecto
  5. Contexto: estado del marcador
  6. ¿Quién se beneficia? (por equipo)
  7. Modelo predictivo

Uso: python lpf/analyze_momentum.py
"""

import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats as scipy_stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler

DATA_PATH       = Path(__file__).parent / "momentum_raw.json"
FORM_PATH       = Path(__file__).parent / "form_data.json"
TEAM_NAMES_PATH = Path(__file__).parent / "team_names.json"
OUT_PATH        = Path(__file__).parent / "momentum_report.html"

# ─────────────────────────────────────────────────────────────────────────────
# 1. CARGA Y PROCESAMIENTO DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    with open(FORM_PATH, encoding="utf-8") as f:
        form = json.load(f)
    team_names = {}
    if TEAM_NAMES_PATH.exists():
        with open(TEAM_NAMES_PATH, encoding="utf-8") as f:
            team_names = json.load(f)
    return raw, form, team_names


def build_team_map(form, raw, team_names=None):
    """
    Mapea event_id -> {home: club, away: club}.
    Prioriza team_names.json (todos los equipos) sobre form_data (solo FIXTURE_CLUBS).
    """
    # Primero: completar con team_names.json si existe
    team_map = {}
    if team_names:
        for eid, t in team_names.items():
            team_map[eid] = {"home": t.get("home"), "away": t.get("away")}

    # Fallback: inferir desde form_data para partidos sin cobertura
    pid_to_club = {pid: pdata["club"] for pid, pdata in form.items()}
    for eid, match in raw.items():
        if eid in team_map and team_map[eid]["home"] and team_map[eid]["away"]:
            continue
        incs = match["incidents"]["incidents"]
        home_club = away_club = None
        for inc in incs:
            inc_type = inc.get("incidentType")
            is_home  = inc.get("isHome")
            if is_home is None:
                continue
            pid = None
            if inc_type in ("goal", "card"):
                pid = str(inc.get("player", {}).get("id", ""))
            elif inc_type == "substitution":
                pid = str(inc.get("playerIn", {}).get("id", ""))
            if pid and pid in pid_to_club:
                club = pid_to_club[pid]
                if is_home and not home_club:
                    home_club = club
                elif not is_home and not away_club:
                    away_club = club
            if home_club and away_club:
                break
        team_map[eid] = {"home": home_club, "away": away_club}

    return team_map


def parse_match(eid, match_data, team_map):
    """
    Retorna dict con presión minuto-a-minuto y eventos parseados.
    pressure[t] > 0 = presión local, < 0 = presión visitante.
    """
    g = match_data.get("graph", {})
    pts = g.get("graphPoints", [])

    # Interpolación a minutos 1-90 exactos
    minute_map = {}
    for p in pts:
        m = int(p["minute"])  # floor para 90.5
        if 1 <= m <= 90:
            minute_map[m] = p["value"]

    # Serie completa 1-90, interpolando huecos
    pressure = {}
    last = 0
    for m in range(1, 91):
        if m in minute_map:
            pressure[m] = minute_map[m]
            last = minute_map[m]
        else:
            pressure[m] = last  # forward fill

    # Parsear incidents
    incs_raw = match_data.get("incidents", {}).get("incidents", [])
    goals = []
    cards = []
    subs  = []

    home_score = away_score = 0
    for inc in incs_raw:
        t     = inc.get("time", 0)
        itype = inc.get("incidentType")
        if not (1 <= t <= 90):
            continue

        if itype == "goal":
            # incidentClass: regular | ownGoal | penalty
            is_home   = inc.get("isHome", True)
            inc_class = inc.get("incidentClass", "regular")
            goals.append({
                "minute":   t,
                "is_home":  is_home,
                "class":    inc_class,
                "home_score_after": inc.get("homeScore", 0),
                "away_score_after": inc.get("awayScore", 0),
            })

        elif itype == "card":
            ctype = inc.get("incidentClass", inc.get("cardType", "yellow"))
            cards.append({
                "minute":    t,
                "is_home":   inc.get("isHome", True),
                "card_type": ctype,
            })

        elif itype == "substitution":
            subs.append({
                "minute":  t,
                "is_home": inc.get("isHome", True),
            })

    teams = team_map.get(eid, {})
    return {
        "eid":      eid,
        "pressure": pressure,
        "goals":    goals,
        "cards":    cards,
        "subs":     subs,
        "home":     teams.get("home"),
        "away":     teams.get("away"),
    }


def get_window(pressure, center, pre=5, post=10):
    """
    Retorna listas pre y post del momento `center`.
    pre:  valores en [center-pre .. center-1]
    post: valores en [center+1 .. center+post]
    """
    pre_vals  = [pressure[m] for m in range(max(1, center - pre), center)
                 if m in pressure]
    post_vals = [pressure[m] for m in range(center + 1, min(91, center + post + 1))
                 if m in pressure]
    return pre_vals, post_vals


# ─────────────────────────────────────────────────────────────────────────────
# 2. ANÁLISIS 1 — ¿EXISTE EL MOMENTUM? (AUTOCORRELACIÓN)
# ─────────────────────────────────────────────────────────────────────────────

def autocorr_at_lag(series, lag):
    if len(series) <= lag:
        return np.nan
    s = np.array(series)
    s = s - s.mean()
    n = len(s)
    cov = np.dot(s[:n-lag], s[lag:]) / n
    var = np.dot(s, s) / n
    return cov / var if var > 0 else 0.0


def analysis_autocorrelation(matches):
    lags = [1, 2, 3, 5, 10]
    lag_values = {lag: [] for lag in lags}

    for m in matches:
        series = [m["pressure"][t] for t in range(1, 91)]
        for lag in lags:
            ac = autocorr_at_lag(series, lag)
            if not np.isnan(ac):
                lag_values[lag].append(ac)

    results = {}
    for lag in lags:
        vals = np.array(lag_values[lag])
        mean_ac = float(np.mean(vals))
        se      = float(np.std(vals) / np.sqrt(len(vals)))
        t_stat, p_val = scipy_stats.ttest_1samp(vals, 0)
        results[lag] = {
            "mean": round(mean_ac, 4),
            "se":   round(se, 4),
            "p":    round(float(p_val), 6),
            "n":    len(vals),
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. ANÁLISIS 2 — PERFIL TEMPORAL DEL PARTIDO
# ─────────────────────────────────────────────────────────────────────────────

def analysis_match_profile(matches):
    by_minute = defaultdict(list)
    for m in matches:
        for t in range(1, 91):
            by_minute[t].append(m["pressure"][t])

    profile = {}
    for t in range(1, 91):
        vals = np.array(by_minute[t])
        profile[t] = {
            "mean": round(float(np.mean(vals)), 3),
            "std":  round(float(np.std(vals)), 3),
            "p75":  round(float(np.percentile(vals, 75)), 3),
            "p25":  round(float(np.percentile(vals, 25)), 3),
        }
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# 4. ANÁLISIS 3 — TRIGGERS: IMPACTO DE EVENTOS
# ─────────────────────────────────────────────────────────────────────────────

def signed_pressure(value, is_home):
    """
    Retorna presión desde la perspectiva del equipo en cuestión.
    Para evento home: positivo = local tiene presión (normal).
    Para evento away: negamos para que positivo = ese equipo tiene presión.
    """
    return value if is_home else -value


def event_windows(matches, event_list_fn, pre=5, post=10):
    """
    Extrae ventanas pre/post para una función que dado un match retorna lista de eventos.
    Normaliza por perspectiva del equipo que protagoniza el evento.
    Retorna lista de (pre_mean, post_mean) por evento.
    """
    records = []
    trajectories = defaultdict(list)  # offset -> list of values

    for m in matches:
        events = event_list_fn(m)
        for ev in events:
            minute  = ev["minute"]
            is_home = ev.get("is_home", True)

            # Ventana
            offsets = list(range(-pre, post + 1))
            traj = {}
            for off in offsets:
                t = minute + off
                if 1 <= t <= 90 and t in m["pressure"]:
                    traj[off] = signed_pressure(m["pressure"][t], is_home)

            if len(traj) < pre + post:  # skip si faltan demasiados datos
                continue

            pre_vals  = [traj[o] for o in range(-pre, 0)  if o in traj]
            post_vals = [traj[o] for o in range(1, post+1) if o in traj]

            if not pre_vals or not post_vals:
                continue

            records.append({
                "pre_mean":  np.mean(pre_vals),
                "post_mean": np.mean(post_vals),
                "delta":     np.mean(post_vals) - np.mean(pre_vals),
                "event":     ev,
            })
            for off, val in traj.items():
                trajectories[off].append(val)

    # Trayectoria promedio
    traj_mean = {}
    traj_se   = {}
    for off in range(-pre, post + 1):
        vals = trajectories[off]
        if vals:
            traj_mean[off] = round(float(np.mean(vals)), 3)
            traj_se[off]   = round(float(np.std(vals) / np.sqrt(len(vals))), 3)

    if not records:
        return {"n": 0, "mean_delta": 0, "p_value": 1.0, "traj_mean": {}, "traj_se": {}}

    deltas  = [r["delta"] for r in records]
    pre_all = [r["pre_mean"] for r in records]
    post_all= [r["post_mean"] for r in records]

    t_stat, p_val = scipy_stats.ttest_rel(post_all, pre_all)

    return {
        "n":          len(records),
        "mean_pre":   round(float(np.mean(pre_all)), 3),
        "mean_post":  round(float(np.mean(post_all)), 3),
        "mean_delta": round(float(np.mean(deltas)), 3),
        "p_value":    round(float(p_val), 6),
        "traj_mean":  {str(k): v for k, v in traj_mean.items()},
        "traj_se":    {str(k): v for k, v in traj_se.items()},
    }


def analysis_triggers(matches):
    results = {}

    # Gol propio (equipo que convierte gana momentum?)
    results["goal_scorer"] = event_windows(
        matches,
        lambda m: [g for g in m["goals"] if g["class"] != "ownGoal"]
    )

    # Gol en contra (equipo que recibe)
    results["goal_conceder"] = event_windows(
        matches,
        lambda m: [{"minute": g["minute"], "is_home": not g["is_home"]}
                   for g in m["goals"] if g["class"] != "ownGoal"]
    )

    # Gol de penal
    results["goal_penalty"] = event_windows(
        matches,
        lambda m: [g for g in m["goals"] if g["class"] == "penalty"]
    )

    # Tarjeta roja / doble amarilla (equipo que queda con 10)
    results["red_card_victim"] = event_windows(
        matches,
        lambda m: [{"minute": c["minute"], "is_home": c["is_home"]}
                   for c in m["cards"] if c["card_type"] in ("red", "yellowRed")]
    )

    # Tarjeta roja — el rival se beneficia
    results["red_card_rival"] = event_windows(
        matches,
        lambda m: [{"minute": c["minute"], "is_home": not c["is_home"]}
                   for c in m["cards"] if c["card_type"] in ("red", "yellowRed")]
    )

    # Amarilla
    results["yellow_card"] = event_windows(
        matches,
        lambda m: [{"minute": c["minute"], "is_home": not c["is_home"]}
                   for c in m["cards"] if c["card_type"] == "yellow"]
    )

    # Sustitución
    results["substitution"] = event_windows(
        matches,
        lambda m: m["subs"]
    )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 5. ANÁLISIS 4 — DURACIÓN DEL EFECTO
# ─────────────────────────────────────────────────────────────────────────────

def analysis_duration(matches, pre=5, post=20):
    """
    Después de un gol, ¿cuántos minutos dura el impulso del equipo que convirtió?
    Usa promedio de la trayectoria minuto a minuto.
    """
    traj_by_offset = defaultdict(list)

    for m in matches:
        for g in m["goals"]:
            if g["class"] == "ownGoal":
                continue
            minute  = g["minute"]
            is_home = g["is_home"]

            for off in range(-pre, post + 1):
                t = minute + off
                if 1 <= t <= 90 and t in m["pressure"]:
                    val = signed_pressure(m["pressure"][t], is_home)
                    traj_by_offset[off].append(val)

    traj  = {}
    se    = {}
    for off in range(-pre, post + 1):
        vals = traj_by_offset[off]
        if vals:
            traj[off] = round(float(np.mean(vals)), 3)
            se[off]   = round(float(np.std(vals) / np.sqrt(len(vals))), 3)

    # Baseline: media pre-evento
    baseline = np.mean([traj[o] for o in range(-pre, 0) if o in traj])

    # Half-life: primer minuto post donde el impulso cae por debajo del 50% del pico
    peak_post = max((traj.get(o, 0) for o in range(1, post + 1)), default=0)
    half_level = baseline + (peak_post - baseline) * 0.5
    half_life = None
    for off in range(1, post + 1):
        if traj.get(off, peak_post) <= half_level:
            half_life = off
            break

    return {
        "traj":      {str(k): v for k, v in traj.items()},
        "se":        {str(k): v for k, v in se.items()},
        "baseline":  round(float(baseline), 3),
        "half_life": half_life,
        "n_goals":   len([g for m in matches for g in m["goals"] if g["class"] != "ownGoal"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. ANÁLISIS 5 — CONTEXTO: ESTADO DEL MARCADOR
# ─────────────────────────────────────────────────────────────────────────────

def analysis_score_state(matches, pre=5, post=10):
    """
    Impacto de gol según contexto: empate->adelante, en ventaja->+2, perdiendo->empate.
    """
    contexts = {
        "go_ahead":        [],   # empate → adelanta (el que convierte pasa de empate a +1)
        "equalizer":       [],   # perdía por 1 → empata (diff_before == -1, resultado empate)
        "extend_lead":     [],   # ya ganaba → amplía
        "pull_one_back":   [],   # perdía por 2+ → acorta (sigue perdiendo)
    }

    for m in matches:
        for g in m["goals"]:
            if g["class"] == "ownGoal":
                continue

            minute  = g["minute"]
            is_home = g["is_home"]
            h_after = g["home_score_after"]
            a_after = g["away_score_after"]

            # Score before goal
            h_before = h_after - (1 if is_home else 0)
            a_before = a_after - (0 if is_home else 1)

            scorer_before = h_before if is_home else a_before
            victim_before = a_before if is_home else h_before

            diff_before = scorer_before - victim_before  # desde perspectiva del que convirtió

            # Clasificar contexto
            if diff_before == 0:
                ctx = "go_ahead"
            elif diff_before == -1:
                # perdía por 1 → empata (equalizer) vs. nunca se usa -1 → empata siempre
                ctx = "equalizer"
            elif diff_before > 0:
                ctx = "extend_lead"
            else:
                ctx = "pull_one_back"  # perdía por 2+ → acorta pero sigue perdiendo

            # Trayectoria signed
            traj_vals = {}
            for off in range(-pre, post + 1):
                t = minute + off
                if 1 <= t <= 90 and t in m["pressure"]:
                    traj_vals[off] = signed_pressure(m["pressure"][t], is_home)

            if len(traj_vals) >= pre + 5:
                contexts[ctx].append(traj_vals)

    result = {}
    for ctx, trajs in contexts.items():
        if not trajs:
            result[ctx] = {"n": 0, "traj": {}}
            continue
        traj_mean = {}
        for off in range(-pre, post + 1):
            vals = [t.get(off) for t in trajs if off in t]
            if vals:
                traj_mean[off] = round(float(np.mean(vals)), 3)
        result[ctx] = {"n": len(trajs), "traj": {str(k): v for k, v in traj_mean.items()}}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 6b. ANÁLISIS EXTRA — CONTEXTO DEL GOL DE EMPATE
# ─────────────────────────────────────────────────────────────────────────────

def analysis_equalizer_context(matches, pre=5, post=10):
    """
    Para los goles del empate (diff_before == -1), separa en dos grupos:
      - 'announced': el equipo ya venia con presion positiva (pre_mean > 0)
      - 'counter':   el equipo aun tenia presion negativa (pre_mean <= 0)
    Retorna trayectorias por grupo y test de significancia entre post-medias.
    """
    from scipy import stats as sp

    groups = {"announced": [], "counter": []}

    for m in matches:
        for g in m["goals"]:
            if g["class"] == "ownGoal":
                continue
            is_home = g["is_home"]
            h_after = g["home_score_after"]
            a_after = g["away_score_after"]
            h_before = h_after - (1 if is_home else 0)
            a_before = a_after - (0 if is_home else 1)
            scorer_before = h_before if is_home else a_before
            victim_before = a_before if is_home else h_before
            diff_before = scorer_before - victim_before

            if diff_before != -1:
                continue

            minute = g["minute"]
            pre_vals = [signed_pressure(m["pressure"][t], is_home)
                        for t in range(max(1, minute - pre), minute)
                        if t in m["pressure"]]
            if not pre_vals:
                continue

            pre_mean = float(np.mean(pre_vals))
            traj = {}
            for off in range(-pre, post + 1):
                t = minute + off
                if 1 <= t <= 90 and t in m["pressure"]:
                    traj[off] = signed_pressure(m["pressure"][t], is_home)

            if len(traj) < pre + 5:
                continue

            group = "announced" if pre_mean > 0 else "counter"
            groups[group].append({"traj": traj, "pre_mean": pre_mean})

    result = {}
    post_means = {}
    for grp, records in groups.items():
        if not records:
            result[grp] = {"n": 0, "traj": {}, "avg_pre": 0}
            post_means[grp] = []
            continue
        traj_mean = {}
        pm = []
        for off in range(-pre, post + 1):
            vals = [r["traj"][off] for r in records if off in r["traj"]]
            if vals:
                traj_mean[off] = round(float(np.mean(vals)), 3)
        for r in records:
            post_vals = [r["traj"][o] for o in range(1, post + 1) if o in r["traj"]]
            if post_vals:
                pm.append(float(np.mean(post_vals)))
        result[grp] = {
            "n":       len(records),
            "traj":    {str(k): v for k, v in traj_mean.items()},
            "avg_pre": round(float(np.mean([r["pre_mean"] for r in records])), 2),
        }
        post_means[grp] = pm

    # Test de significancia entre los dos grupos
    a = post_means.get("announced", [])
    c = post_means.get("counter", [])
    p_value = 1.0
    if len(a) >= 5 and len(c) >= 5:
        _, p_value = sp.ttest_ind(a, c)

    result["p_value"]    = round(float(p_value), 4)
    result["significant"] = p_value < 0.05
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7. ANÁLISIS 6 — ¿QUIÉN SE BENEFICIA? (POR EQUIPO)
# ─────────────────────────────────────────────────────────────────────────────

def analysis_teams(matches):
    team_stats = defaultdict(lambda: {
        "mins_positive": 0,   # minutos con presión positiva (cuando son local)
        "mins_negative": 0,   # minutos con presión positiva (cuando son visitante → negamos)
        "total_mins":    0,
        "goals_scored":  0,
        "goals_conceded":0,
        "goals_high_mom":  0,  # goles con momentum > +10 antes
        "goals_low_mom":   0,  # goles con momentum <= 0 antes
    })

    for m in matches:
        home = m.get("home")
        away = m.get("away")
        if not home and not away:
            continue

        series = [m["pressure"][t] for t in range(1, 91)]

        # Minutos con presión favorable para cada equipo
        if home:
            team_stats[home]["mins_positive"] += sum(1 for v in series if v > 10)
            team_stats[home]["total_mins"]    += 90

        if away:
            team_stats[away]["mins_negative"] += sum(1 for v in series if v < -10)
            team_stats[away]["total_mins"]    += 90

        # Goles
        for g in m["goals"]:
            if g["class"] == "ownGoal":
                continue
            t       = g["minute"]
            is_home = g["is_home"]
            scorer  = home if is_home else away
            victim  = away if is_home else home

            if scorer:
                team_stats[scorer]["goals_scored"] += 1
                # Momentum 5 min antes
                pre_vals = [m["pressure"][mt] for mt in range(max(1,t-5), t) if mt in m["pressure"]]
                if pre_vals:
                    pre_signed = np.mean(pre_vals) if is_home else -np.mean(pre_vals)
                    if pre_signed > 10:
                        team_stats[scorer]["goals_high_mom"] += 1
                    else:
                        team_stats[scorer]["goals_low_mom"] += 1

            if victim:
                team_stats[victim]["goals_conceded"] += 1

    # Calcular métricas derivadas
    result = {}
    for team, s in team_stats.items():
        if s["total_mins"] < 90:  # ignorar equipos con muy poca data
            continue
        total_goals = s["goals_scored"]
        result[team] = {
            "pct_dominant":    round(100 * (s["mins_positive"] + s["mins_negative"]) / max(s["total_mins"], 1), 1),
            "goals_scored":    s["goals_scored"],
            "goals_conceded":  s["goals_conceded"],
            "goals_high_mom":  s["goals_high_mom"],
            "goals_low_mom":   s["goals_low_mom"],
            "pct_goals_in_momentum": round(100 * s["goals_high_mom"] / max(total_goals, 1), 1),
            "total_mins":      s["total_mins"],
        }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 8. ANÁLISIS 7 — MODELO PREDICTIVO
# ─────────────────────────────────────────────────────────────────────────────

def analysis_predictive(matches):
    """
    Pregunta: dada la presión de los últimos 5 minutos + contexto,
    ¿se puede predecir qué equipo mete el próximo gol?

    Target: 1 = equipo con momentum positivo mete el siguiente gol
            0 = equipo con momentum negativo mete el siguiente gol
    """
    X_rows = []
    y_rows = []

    for m in matches:
        # Ordenar goles por minuto
        goals = sorted([g for g in m["goals"] if g["class"] != "ownGoal"],
                       key=lambda g: g["minute"])
        if len(goals) < 2:
            continue

        for i, g in enumerate(goals):
            minute  = g["minute"]
            is_home = g["is_home"]

            if minute < 6:
                continue

            # Features al momento del gol
            last5 = [m["pressure"][t] for t in range(minute - 5, minute) if t in m["pressure"]]
            if not last5:
                continue
            avg_mom = float(np.mean(last5))

            # Score state antes del gol
            h_before = g["home_score_after"] - (1 if is_home else 0)
            a_before = g["away_score_after"] - (0 if is_home else 1)
            score_diff = float(h_before - a_before)  # home perspective

            # Minute bucket (0=1-30, 1=31-60, 2=61-90)
            min_bucket = min(2, (minute - 1) // 30)

            # Absolute momentum (home perspective)
            x = [avg_mom, score_diff, float(min_bucket), avg_mom ** 2]
            X_rows.append(x)

            # Label: was the scoring team having positive momentum?
            # is_home=True and avg_mom>0 → scoring team was dominant → label 1
            # is_home=False and avg_mom<0 → scoring team was dominant → label 1
            label = 1 if (is_home and avg_mom > 0) or (not is_home and avg_mom < 0) else 0
            y_rows.append(label)

    if len(X_rows) < 30:
        return {"error": "Insuficientes datos para el modelo"}

    X = np.array(X_rows)
    y = np.array(y_rows)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(max_iter=500)
    model.fit(X_scaled, y)

    y_prob = model.predict_proba(X_scaled)[:, 1]
    auc    = roc_auc_score(y, y_prob)

    fpr, tpr, _ = roc_curve(y, y_prob)

    # Base rate
    base_rate = float(np.mean(y))

    # Feature importances (coeficientes)
    feature_names = ["Momentum avg (5min)", "Diferencia marcador", "Tiempo del partido", "Momentum²"]
    coefs = model.coef_[0].tolist()

    # Momentum buckets → win rate
    buckets = [-50, -20, -10, -5, 0, 5, 10, 20, 50]
    bucket_labels = []
    bucket_rates  = []
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i+1]
        mask = (X[:, 0] >= lo) & (X[:, 0] < hi)
        if mask.sum() > 5:
            bucket_labels.append(f"{lo} a {hi}")
            bucket_rates.append(round(float(np.mean(y[mask])), 3))

    return {
        "n":              len(y),
        "auc":            round(auc, 4),
        "base_rate":      round(base_rate, 3),
        "fpr":            [round(v, 4) for v in fpr.tolist()],
        "tpr":            [round(v, 4) for v in tpr.tolist()],
        "feature_names":  feature_names,
        "coefs":          [round(c, 4) for c in coefs],
        "bucket_labels":  bucket_labels,
        "bucket_rates":   bucket_rates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. ESTADÍSTICAS GLOBALES
# ─────────────────────────────────────────────────────────────────────────────

def global_stats(matches):
    all_pressures = []
    all_goals = []
    n_reds = 0
    n_yellows = 0
    n_subs = 0

    for m in matches:
        for t in range(1, 91):
            all_pressures.append(m["pressure"][t])
        all_goals.extend(m["goals"])
        n_reds   += sum(1 for c in m["cards"] if c["card_type"] in ("red", "yellowRed"))
        n_yellows+= sum(1 for c in m["cards"] if c["card_type"] == "yellow")
        n_subs   += len(m["subs"])

    p = np.array(all_pressures)
    return {
        "n_matches":    len(matches),
        "n_goals":      len(all_goals),
        "n_reds":       n_reds,
        "n_yellows":    n_yellows,
        "n_subs":       n_subs,
        "avg_goals_per_match": round(len(all_goals) / len(matches), 2),
        "pct_home_positive":   round(100 * np.mean(p > 0), 1),
        "mean_abs_pressure":   round(float(np.mean(np.abs(p))), 2),
        "goals_by_home":       sum(1 for g in all_goals if g["is_home"]),
        "goals_by_away":       sum(1 for g in all_goals if not g["is_home"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. GENERACIÓN HTML
# ─────────────────────────────────────────────────────────────────────────────

def build_html(results):
    ac      = results["autocorr"]
    profile = results["profile"]
    trig    = results["triggers"]
    dur     = results["duration"]
    score   = results["score_state"]
    teams   = results["teams"]
    pred    = results["predictive"]
    glob    = results["global"]

    # Helpers para serializar datos como JS
    def js(obj):
        return json.dumps(obj, ensure_ascii=False)

    # ── Preparar datos para gráficos ──────────────────────────────────────────

    # Autocorrelación
    ac_lags  = list(ac.keys())
    ac_means = [ac[l]["mean"] for l in ac_lags]
    ac_ses   = [ac[l]["se"]   for l in ac_lags]
    ac_ps    = [ac[l]["p"]    for l in ac_lags]

    # Perfil del partido
    mins      = list(range(1, 91))
    prof_mean = [profile[m]["mean"] for m in mins]
    prof_p75  = [profile[m]["p75"]  for m in mins]
    prof_p25  = [profile[m]["p25"]  for m in mins]

    # Triggers — resumen en barras
    event_labels = {
        "goal_scorer":     "Gol (team que convierte)",
        "goal_conceder":   "Gol (team que recibe)",
        "red_card_victim": "Roja (equipo sancionado)",
        "red_card_rival":  "Roja (equipo beneficiado)",
        "yellow_card":     "Amarilla (rival beneficiado)",
        "substitution":    "Sustitución",
    }
    trig_names  = []
    trig_pre    = []
    trig_post   = []
    trig_delta  = []
    trig_p      = []
    trig_n      = []
    for key, label in event_labels.items():
        if key in trig and trig[key]["n"] > 0:
            trig_names.append(label)
            trig_pre.append(trig[key]["mean_pre"])
            trig_post.append(trig[key]["mean_post"])
            trig_delta.append(trig[key]["mean_delta"])
            trig_p.append(trig[key]["p_value"])
            trig_n.append(trig[key]["n"])

    # Trayectorias triggers (gol del que convierte vs roja)
    def traj_to_xy(traj_dict, offsets):
        keys = [str(o) for o in offsets]
        return [traj_dict.get(k) for k in keys]

    offsets_short = list(range(-5, 11))
    offsets_long  = list(range(-5, 21))

    goal_traj    = traj_to_xy(trig.get("goal_scorer", {}).get("traj_mean", {}), offsets_short)
    concede_traj = traj_to_xy(trig.get("goal_conceder", {}).get("traj_mean", {}), offsets_short)
    red_v_traj   = traj_to_xy(trig.get("red_card_victim", {}).get("traj_mean", {}), offsets_short)
    red_r_traj   = traj_to_xy(trig.get("red_card_rival", {}).get("traj_mean", {}), offsets_short)

    # Duración del gol
    dur_offsets  = list(range(-5, 21))
    dur_traj     = [dur["traj"].get(str(o)) for o in dur_offsets]
    dur_se       = [dur["se"].get(str(o)) for o in dur_offsets]
    dur_upper    = [t + s if t is not None and s is not None else None for t, s in zip(dur_traj, dur_se)]
    dur_lower    = [t - s if t is not None and s is not None else None for t, s in zip(dur_traj, dur_se)]

    # Score state
    ctx_labels = {
        "go_ahead":      "Gol que adelanta",
        "extend_lead":   "Gol que amplía ventaja",
        "pull_one_back": "Gol de descuento",
    }
    score_traces = []
    for ctx, label in ctx_labels.items():
        if ctx in score and score[ctx]["n"] > 0:
            traj = score[ctx]["traj"]
            score_traces.append({
                "name": f"{label} (n={score[ctx]['n']})",
                "x":    [str(o) for o in offsets_short],
                "y":    traj_to_xy(traj, offsets_short),
            })

    # Teams — top 12 por dominancia
    team_list = sorted(teams.items(), key=lambda x: -x[1]["pct_dominant"])[:14]
    team_names = [t[0] for t in team_list]
    team_pcts  = [t[1]["pct_dominant"] for t in team_list]
    team_conv  = [t[1]["pct_goals_in_momentum"] for t in team_list]

    # Predictivo
    pred_ok = "auc" in pred

    # ── Pre-compute HTML fragments (avoid nested f-strings in Python 3.9) ─────

    # AC table rows
    ac_rows = ""
    for lag in ac_lags:
        vc  = "pos" if ac[lag]["mean"] > 0 else "neg"
        sc  = "sig" if ac[lag]["p"] < 0.05 else "nosig"
        st  = "Si (p&lt;0.05)" if ac[lag]["p"] < 0.05 else "No"
        ac_rows += (f'<tr><td>+{lag} min</td>'
                    f'<td class="{vc}">{ac[lag]["mean"]:.4f}</td>'
                    f'<td>{ac[lag]["p"]:.4f}</td>'
                    f'<td class="{sc}">{st}</td></tr>\n')

    # AC insight text
    if ac[1]["p"] < 0.05:
        ac_sig_txt = "estadisticamente significativa &#8212; el momentum <strong>existe</strong> como fenomeno estadistico en la LPF."
    else:
        ac_sig_txt = "no alcanza significancia estadistica a nivel individual, aunque hay tendencia positiva."
    first_nosig = next((l for l in ac_lags if ac[l]["p"] > 0.05), None)
    ac_persist_txt = f"~{first_nosig} minutos" if first_nosig else "los 10 minutos analizados"

    # Triggers table rows
    trig_rows = ""
    for name, pre, post, delta, p, n in zip(trig_names, trig_pre, trig_post, trig_delta, trig_p, trig_n):
        dc  = "pos" if delta >= 0 else "neg"
        ds  = "+" if delta >= 0 else ""
        sc  = "sig" if p < 0.05 else "nosig"
        st  = "Si" if p < 0.05 else "No"
        trig_rows += (f'<tr><td>{name}</td><td>{n}</td>'
                      f'<td>{pre:.1f}</td><td>{post:.1f}</td>'
                      f'<td class="{dc}">{ds}{delta:.1f}</td>'
                      f'<td>{p:.4f}</td><td class="{sc}">{st}</td></tr>\n')

    # Half-life text
    hl_display = str(dur["half_life"]) + " min" if dur["half_life"] else "20+"
    hl_val     = str(dur["half_life"]) if dur["half_life"] else "mas de 20"
    if dur["half_life"] and dur["half_life"] <= 5:
        hl_interp = "es corta &#8212; el rival responde rapido."
    elif dur["half_life"] and dur["half_life"] <= 10:
        hl_interp = "dura un bloque tactico completo."
    else:
        hl_interp = "persiste durante un periodo significativo del partido."

    # Predictive section HTML + JS
    if pred_ok:
        feat_rows = ""
        for i, (name, c) in enumerate(zip(pred["feature_names"], pred["coefs"])):
            cc   = "pos" if c >= 0 else "neg"
            cs   = "+" if c >= 0 else ""
            interp = "Momentum positivo aumenta probabilidad de que el equipo dominante convierta" if i == 0 else "Efectos contextuales"
            feat_rows += (f'<tr><td>{name}</td>'
                          f'<td class="{cc}">{cs}{c:.4f}</td>'
                          f'<td style="color:var(--muted);font-size:.8rem">{interp}</td></tr>\n')
        if pred["auc"] > 0.55:
            auc_txt = "Un AUC &gt; 0.55 indica que el momentum tiene poder predictivo real sobre quien mete el siguiente gol."
        else:
            auc_txt = "El AUC esta cerca del azar (0.5), lo que sugiere que el momentum de SofaScore por si solo no predice bien al goleador siguiente."
        base_pct = f"{pred['base_rate']:.1%}"
        pred_html = (
            f'<div class="grid-2">'
            f'<div class="card"><h3>Curva ROC (AUC = {pred["auc"]:.4f})</h3>'
            f'<div id="chart-roc" class="chart"></div></div>'
            f'<div class="card"><h3>Tasa de goles con momentum por rango de presion</h3>'
            f'<div id="chart-pred-buckets" class="chart"></div></div></div>'
            f'<div class="card" style="margin-top:1.5rem">'
            f'<h3>Coeficientes del modelo</h3>'
            f'<table><tr><th>Feature</th><th>Coeficiente</th><th>Interpretacion</th></tr>'
            f'{feat_rows}</table>'
            f'<div class="insight"><strong>AUC = {pred["auc"]:.3f}</strong> (base rate: {base_pct}). {auc_txt}</div>'
            f'</div>'
        )
        pred_js = (
            f'(function() {{\n'
            f'  const fpr    = {js(pred["fpr"])};\n'
            f'  const tpr    = {js(pred["tpr"])};\n'
            f'  const labels = {js(pred["bucket_labels"])};\n'
            f'  const rates  = {js(pred["bucket_rates"])};\n'
            f'  const base   = {js(float(pred["base_rate"]))};\n'
            f'  const roc = {{x:fpr, y:tpr, type:"scatter", mode:"lines",'
            f'    line:{{color:BLUE, width:2}}, name:"ROC (AUC={pred["auc"]:.3f})"}};\n'
            f'  const diag = {{x:[0,1], y:[0,1], type:"scatter", mode:"lines",'
            f'    line:{{color:"#555", dash:"dot", width:1}}, showlegend:false}};\n'
            f'  Plotly.newPlot("chart-roc", [roc, diag],'
            f'    layout("", {{title:"Tasa Falsos Positivos"}}, {{title:"Tasa Verdaderos Positivos"}}), cfg);\n'
            f'  const bucket_colors = rates.map(r => r > base*1.1 ? GREEN : r < base*0.9 ? ORANGE : BLUE);\n'
            f'  const base_ln = {{x:[labels[0], labels[labels.length-1]], y:[base, base],'
            f'    type:"scatter", mode:"lines", line:{{color:"#555", dash:"dot", width:1}},'
            f'    name:`Base rate (${{(base*100).toFixed(1)}}%)`, showlegend:true}};\n'
            f'  const bbar = {{x:labels, y:rates, type:"bar", marker:{{color:bucket_colors}}, name:"Tasa gol en momentum"}};\n'
            f'  Plotly.newPlot("chart-pred-buckets", [bbar, base_ln],'
            f'    layout("", {{title:"Rango de presion promedio (5 min pre-gol)"}},'
            f'               {{title:"% goles donde equipo dominante convierte"}}), cfg);\n'
            f'}})();\n'
        )
    else:
        pred_html = f'<div class="insight"><strong>Error:</strong> {pred.get("error","")}</div>'
        pred_js   = ""

    # ── HTML ─────────────────────────────────────────────────────────────────

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Análisis de Momentum — LPF 2026</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg: #0d0f14;
    --surface: #161a22;
    --surface2: #1e2530;
    --border: #2a3040;
    --accent: #4e9eff;
    --accent2: #ff6b4e;
    --green: #4eff8e;
    --yellow: #ffe34e;
    --text: #e8eaf0;
    --muted: #7a8494;
    --font: 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.5; }}

  /* NAV */
  nav {{
    position: sticky; top: 0; z-index: 100;
    background: rgba(13,15,20,0.96); backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
    display: flex; align-items: center; gap: 0;
  }}
  nav .logo {{ font-size: .85rem; font-weight: 700; color: var(--accent); padding: 1rem 1.5rem 1rem 0; border-right: 1px solid var(--border); margin-right: 1rem; white-space: nowrap; }}
  nav a {{ color: var(--muted); text-decoration: none; font-size: .8rem; padding: .85rem .9rem; white-space: nowrap; transition: color .15s; }}
  nav a:hover {{ color: var(--text); }}

  /* LAYOUT */
  .hero {{
    padding: 4rem 2rem 3rem;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(135deg, #0d0f14 60%, #131828);
  }}
  .hero h1 {{ font-size: 2.2rem; font-weight: 800; letter-spacing: -.02em; }}
  .hero h1 span {{ color: var(--accent); }}
  .hero p {{ color: var(--muted); margin-top: .6rem; max-width: 640px; font-size: .95rem; }}
  .kpi-row {{ display: flex; gap: 1.2rem; margin-top: 2rem; flex-wrap: wrap; }}
  .kpi {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem 1.4rem; min-width: 140px;
  }}
  .kpi .val {{ font-size: 1.8rem; font-weight: 800; color: var(--accent); }}
  .kpi .lbl {{ font-size: .75rem; color: var(--muted); margin-top: .2rem; }}

  section {{
    padding: 3rem 2rem;
    border-bottom: 1px solid var(--border);
  }}
  section h2 {{
    font-size: 1.3rem; font-weight: 700; margin-bottom: .4rem;
    display: flex; align-items: center; gap: .6rem;
  }}
  section h2 .num {{
    background: var(--accent); color: #000; font-size: .7rem;
    border-radius: 4px; padding: .15rem .4rem; font-weight: 800;
  }}
  .subtitle {{ color: var(--muted); font-size: .85rem; margin-bottom: 2rem; max-width: 700px; }}

  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.5rem; }}
  @media (max-width: 900px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}

  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.2rem; overflow: hidden;
  }}
  .card h3 {{ font-size: .85rem; color: var(--muted); margin-bottom: 1rem; text-transform: uppercase; letter-spacing: .05em; }}

  .chart {{ width: 100%; height: 320px; }}
  .chart-tall {{ width: 100%; height: 400px; }}

  /* INSIGHT BOX */
  .insight {{
    background: var(--surface2); border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0; padding: .9rem 1.2rem;
    font-size: .85rem; margin-top: 1.5rem; color: var(--text);
  }}
  .insight strong {{ color: var(--accent); }}

  /* TABLE */
  table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
  th {{ color: var(--muted); text-align: left; padding: .5rem .8rem; border-bottom: 1px solid var(--border); font-weight: 600; }}
  td {{ padding: .5rem .8rem; border-bottom: 1px solid rgba(42,48,64,.5); }}
  tr:hover td {{ background: var(--surface2); }}
  .sig {{ color: var(--green); font-weight: 700; }}
  .nosig {{ color: var(--muted); }}
  .pos {{ color: var(--accent); }}
  .neg {{ color: var(--accent2); }}

  footer {{ padding: 2rem; text-align: center; color: var(--muted); font-size: .75rem; }}
</style>
</head>
<body>

<nav>
  <div class="logo">LPF 2026 · Momentum</div>
  <a href="#existencia">1. Existencia</a>
  <a href="#perfil">2. Perfil</a>
  <a href="#triggers">3. Triggers</a>
  <a href="#duracion">4. Duración</a>
  <a href="#marcador">5. Marcador</a>
  <a href="#equipos">6. Equipos</a>
  <a href="#modelo">7. Modelo</a>
</nav>

<!-- HERO -->
<div class="hero">
  <h1>Momentum en la <span>LPF 2026</span></h1>
  <p>Análisis estadístico intra-partido basado en {glob['n_matches']} partidos, {glob['n_goals']} goles y {glob['n_reds']} tarjetas rojas. Fuente: SofaScore Pressure Graph.</p>
  <div class="kpi-row">
    <div class="kpi"><div class="val">{glob['n_matches']}</div><div class="lbl">Partidos analizados</div></div>
    <div class="kpi"><div class="val">{glob['n_goals']}</div><div class="lbl">Goles registrados</div></div>
    <div class="kpi"><div class="val">{glob['avg_goals_per_match']}</div><div class="lbl">Goles por partido</div></div>
    <div class="kpi"><div class="val">{glob['pct_home_positive']}%</div><div class="lbl">Tiempo con presión local</div></div>
    <div class="kpi"><div class="val">{glob['n_reds']}</div><div class="lbl">Tarjetas rojas</div></div>
    <div class="kpi"><div class="val">{glob['n_yellows']}</div><div class="lbl">Tarjetas amarillas</div></div>
  </div>
</div>

<!-- ───────────────────── SECCIÓN 1: EXISTENCIA ───────────────────────────── -->
<section id="existencia">
  <h2><span class="num">01</span> ¿Existe el momentum?</h2>
  <p class="subtitle">Si el momentum es real, los valores de presión de un minuto deben correlacionar con los del minuto siguiente. Testeamos autocorrelación en los {glob['n_matches']} partidos a distintos rezagos.</p>

  <div class="grid-2">
    <div class="card">
      <h3>Autocorrelación por rezago (promedio ± SE)</h3>
      <div id="chart-ac" class="chart"></div>
    </div>
    <div class="card">
      <h3>Interpretación estadística</h3>
      <table>
        <tr><th>Rezago</th><th>AC promedio</th><th>p-valor</th><th>Significativo</th></tr>
        {ac_rows}
      </table>
      <div class="insight">
        <strong>Conclusion:</strong> La autocorrelacion de lag-1 es
        <strong>{ac[1]['mean']:.3f}</strong> (p={ac[1]['p']:.4f}),
        {ac_sig_txt}
        La presion tiende a persistir hasta {ac_persist_txt}.
      </div>
    </div>
  </div>
</section>

<!-- ───────────────────── SECCIÓN 2: PERFIL ──────────────────────────────── -->
<section id="perfil">
  <h2><span class="num">02</span> Perfil temporal del partido</h2>
  <p class="subtitle">¿La presión tiene una forma característica a lo largo de los 90 minutos? Promedio y banda intercuartil de los {glob['n_matches']} partidos.</p>

  <div class="card">
    <h3>Presión promedio minuto a minuto (positivo = local, negativo = visitante)</h3>
    <div id="chart-profile" class="chart-tall"></div>
  </div>
  <div class="insight" style="margin-top:1.5rem">
    <strong>Lectura:</strong> La línea central es la media. La banda muestra el rango intercuartil (50% de los partidos).
    Valores cercanos a 0 indican equilibrio de presión entre los equipos.
    Un desplazamiento positivo sostenido refleja ventaja estructural del equipo local.
  </div>
</section>

<!-- ───────────────────── SECCIÓN 3: TRIGGERS ────────────────────────────── -->
<section id="triggers">
  <h2><span class="num">03</span> Triggers: ¿qué genera momentum?</h2>
  <p class="subtitle">Para cada tipo de evento, medimos el cambio promedio en presión entre los 5 minutos previos y los 10 minutos posteriores (desde la perspectiva del equipo protagonista del evento).</p>

  <div class="grid-2">
    <div class="card">
      <h3>Variación de presión pre→post por evento (delta)</h3>
      <div id="chart-triggers-bar" class="chart"></div>
    </div>
    <div class="card">
      <h3>Trayectoria de presión alrededor del evento</h3>
      <div id="chart-triggers-traj" class="chart"></div>
    </div>
  </div>

  <div class="card" style="margin-top:1.5rem">
    <h3>Tabla de impacto por evento</h3>
    <table>
      <tr><th>Evento</th><th>N casos</th><th>Pre (avg)</th><th>Post (avg)</th><th>Delta</th><th>p-valor</th><th>Significativo</th></tr>
      {trig_rows}
    </table>
  </div>
</section>

<!-- ───────────────────── SECCIÓN 4: DURACIÓN ────────────────────────────── -->
<section id="duracion">
  <h2><span class="num">04</span> ¿Cuánto dura el impulso?</h2>
  <p class="subtitle">Después de un gol, ¿cuántos minutos sostiene el equipo que convirtió su ventaja de presión? Análisis de {dur['n_goals']} goles regulares.</p>

  <div class="grid-2">
    <div class="card">
      <h3>Trayectoria de presión post-gol (equipo que convierte)</h3>
      <div id="chart-duration" class="chart-tall"></div>
    </div>
    <div class="card" style="display:flex;flex-direction:column;gap:1rem;">
      <h3>Métricas de duración</h3>
      <div class="kpi"><div class="val">{hl_display}</div><div class="lbl">Semi-vida del impulso post-gol</div></div>
      <div class="kpi"><div class="val">{dur['baseline']:.1f}</div><div class="lbl">Nivel base de presion (pre-gol)</div></div>
      <div class="kpi"><div class="val">{dur['n_goals']}</div><div class="lbl">Goles analizados</div></div>
      <div class="insight">
        <strong>Semi-vida:</strong> El impulso de presion post-gol tarda aproximadamente
        <strong>{hl_val} minutos</strong>
        en reducirse a la mitad. Sugiere que la ventaja de momentum post-gol {hl_interp}
      </div>
    </div>
  </div>
</section>

<!-- ───────────────────── SECCIÓN 5: MARCADOR ────────────────────────────── -->
<section id="marcador">
  <h2><span class="num">05</span> Contexto: estado del marcador</h2>
  <p class="subtitle">¿El impulso post-gol varía según el contexto del marcador? Comparamos tres situaciones: el gol que adelanta, el que amplía ventaja, y el de descuento.</p>

  <div class="card">
    <h3>Trayectoria de presión según contexto del gol (desde perspectiva del equipo que convierte)</h3>
    <div id="chart-score" class="chart-tall"></div>
  </div>
</section>

<!-- ───────────────────── SECCIÓN 6: EQUIPOS ─────────────────────────────── -->
<section id="equipos">
  <h2><span class="num">06</span> ¿Quién se beneficia?</h2>
  <p class="subtitle">Equipos rankeados por porcentaje de tiempo con presión dominante (>10 puntos). Nota: solo equipos con jugadores en form_data.</p>

  <div class="grid-2">
    <div class="card">
      <h3>% de tiempo con presión dominante por equipo</h3>
      <div id="chart-teams-dom" class="chart-tall"></div>
    </div>
    <div class="card">
      <h3>% de goles convertidos con momentum previo positivo</h3>
      <div id="chart-teams-conv" class="chart-tall"></div>
    </div>
  </div>
</section>

<!-- ───────────────────── SECCIÓN 7: MODELO ──────────────────────────────── -->
<section id="modelo">
  <h2><span class="num">07</span> ¿Se puede predecir?</h2>
  <p class="subtitle">Modelo logístico: dado el momentum de los últimos 5 minutos + estado del marcador + momento del partido, ¿el equipo dominante convierte?</p>

  {pred_html}
</section>

<footer>
  Fuente: SofaScore API · LPF Primera División 2026 · {glob['n_matches']} partidos · Análisis: Franco Analytics
</footer>

<script>
// ─── Plot config ──────────────────────────────────────────────────────────────
const cfg = {{responsive: true}};
const layout = (title, xaxis={{}}, yaxis={{}}, extra={{}}) => ({{
  title: {{text:'', font:{{size:12}}}},
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor:  'rgba(0,0,0,0)',
  font:  {{color:'#e8eaf0', size:11}},
  xaxis: {{gridcolor:'#2a3040', zerolinecolor:'#3a4555', ...xaxis}},
  yaxis: {{gridcolor:'#2a3040', zerolinecolor:'#3a4555', ...yaxis}},
  margin: {{t:20, r:20, b:50, l:55}},
  showlegend: true,
  legend: {{bgcolor:'rgba(0,0,0,0)', bordercolor:'#2a3040', borderwidth:1}},
  ...extra
}});
const BLUE   = '#4e9eff';
const ORANGE = '#ff6b4e';
const GREEN  = '#4eff8e';
const YELLOW = '#ffe34e';
const PURPLE = '#b44eff';

// ─── 1. Autocorrelación ───────────────────────────────────────────────────────
(function() {{
  const lags    = {js(ac_lags)};
  const means   = {js(ac_means)};
  const ses     = {js(ac_ses)};

  const colors  = means.map(v => v > 0 ? BLUE : ORANGE);
  const trace   = {{
    x: lags.map(l => `Lag ${{l}}`),
    y: means,
    error_y: {{type:'data', array:ses, visible:true, color:'#555', thickness:1.5, width:4}},
    type: 'bar',
    marker: {{color: colors}},
    name: 'AC promedio',
  }};
  const baseline = {{x:['Lag 1','Lag 10'], y:[0,0], type:'scatter', mode:'lines',
                     line:{{color:'#555',dash:'dot',width:1}}, showlegend:false}};

  Plotly.newPlot('chart-ac', [trace, baseline],
    layout('', {{title:'Rezago (minutos)'}}, {{title:'Autocorrelación promedio'}}),
    cfg);
}})();

// ─── 2. Perfil del partido ────────────────────────────────────────────────────
(function() {{
  const mins  = {js(mins)};
  const mean_ = {js(prof_mean)};
  const p75   = {js(prof_p75)};
  const p25   = {js(prof_p25)};

  const band_upper = {{x:[...mins, ...mins.slice().reverse()],
    y:[...p75, ...p25.slice().reverse()],
    fill:'toself', fillcolor:'rgba(78,158,255,0.1)',
    line:{{color:'transparent'}}, showlegend:true, name:'Rango intercuartil',type:'scatter'}};
  const mean_line = {{x:mins, y:mean_, type:'scatter', mode:'lines',
    line:{{color:BLUE, width:2}}, name:'Media'}};
  const zero_line = {{x:[1,90], y:[0,0], type:'scatter', mode:'lines',
    line:{{color:'#555', dash:'dot', width:1}}, showlegend:false}};
  const ht_line   = {{x:[45,45], y:[-30,30], type:'scatter', mode:'lines',
    line:{{color:'#444', dash:'dash', width:1}}, name:'Mediotiempo', showlegend:true}};

  Plotly.newPlot('chart-profile', [band_upper, mean_line, zero_line, ht_line],
    layout('', {{title:'Minuto'}}, {{title:'Índice de presión (+ = local)'}},
           {{height:380}}), cfg);
}})();

// ─── 3. Triggers — barras delta ───────────────────────────────────────────────
(function() {{
  const names  = {js(trig_names)};
  const deltas = {js(trig_delta)};
  const ps     = {js(trig_p)};
  const ns     = {js(trig_n)};

  const colors = deltas.map((d,i) => ps[i] < 0.05 ? (d>0 ? GREEN : ORANGE) : '#3a4555');
  const trace  = {{
    y: names, x: deltas, type:'bar', orientation:'h',
    marker: {{color: colors}},
    text: ns.map(n => `n=${{n}}`),
    textposition: 'outside',
    textfont: {{color:'#7a8494', size:10}},
    name: 'Delta presión',
  }};
  const zero = {{x:[0,0], y:[names[0], names[names.length-1]], type:'scatter', mode:'lines',
    line:{{color:'#555',dash:'dot',width:1}}, showlegend:false}};

  Plotly.newPlot('chart-triggers-bar', [trace, zero],
    layout('', {{title:'Delta presión (post − pre)', zeroline:true}},
               {{automargin:true}}), cfg);
}})();

// ─── 3b. Triggers — trayectorias ─────────────────────────────────────────────
(function() {{
  const offs   = {js(list(range(-5, 11)))};
  const goal   = {js(goal_traj)};
  const conc   = {js(concede_traj)};
  const redv   = {js(red_v_traj)};
  const redr   = {js(red_r_traj)};

  const traces = [
    {{x:offs, y:goal, type:'scatter', mode:'lines', name:'Gol (convierte)', line:{{color:GREEN, width:2}}}},
    {{x:offs, y:conc, type:'scatter', mode:'lines', name:'Gol (recibe)',    line:{{color:ORANGE, width:2}}}},
    {{x:offs, y:redv, type:'scatter', mode:'lines', name:'Roja (sancionado)',  line:{{color:'#ff4e4e', width:2, dash:'dot'}}}},
    {{x:offs, y:redr, type:'scatter', mode:'lines', name:'Roja (beneficiado)', line:{{color:BLUE, width:2, dash:'dot'}}}},
  ].filter(t => t.y.some(v => v !== null));

  const vline = {{x:[0,0], y:[-30,30], type:'scatter', mode:'lines',
    line:{{color:'#555', dash:'dash', width:1}}, showlegend:false, name:'Evento'}};

  Plotly.newPlot('chart-triggers-traj', [...traces, vline],
    layout('', {{title:'Minutos desde el evento'}},
               {{title:'Presión (perspectiva del equipo protagonista)'}}), cfg);
}})();

// ─── 4. Duración ─────────────────────────────────────────────────────────────
(function() {{
  const offs  = {js(dur_offsets)};
  const traj  = {js(dur_traj)};
  const upper = {js(dur_upper)};
  const lower = {js(dur_lower)};
  const base  = {js(float(dur['baseline']))};

  const band = {{
    x:[...offs, ...offs.slice().reverse()],
    y:[...upper, ...lower.slice().reverse()],
    fill:'toself', fillcolor:'rgba(78,158,255,0.1)',
    line:{{color:'transparent'}}, showlegend:true, name:'± 1 SE',type:'scatter'
  }};
  const line = {{x:offs, y:traj, type:'scatter', mode:'lines',
    line:{{color:BLUE, width:2.5}}, name:'Presión promedio (equipo que convierte)'}};
  const base_line = {{x:[offs[0], offs[offs.length-1]], y:[base,base], type:'scatter', mode:'lines',
    line:{{color:'#555', dash:'dot', width:1}}, showlegend:true, name:'Nivel base (pre-gol)'}};
  const vline = {{x:[0,0], y:[-30,50], type:'scatter', mode:'lines',
    line:{{color:GREEN, dash:'dash', width:1.5}}, showlegend:true, name:'Gol (minuto 0)'}};

  Plotly.newPlot('chart-duration', [band, line, base_line, vline],
    layout('', {{title:'Minutos desde el gol'}},
               {{title:'Presión promedio (perspectiva del que convierte)'}},
               {{height:380}}), cfg);
}})();

// ─── 5. Score state ───────────────────────────────────────────────────────────
(function() {{
  const traces_data = {js(score_traces)};
  const colors = [GREEN, BLUE, ORANGE, YELLOW, PURPLE];
  const traces = traces_data.map((t,i) => ({{
    x: t.x.map(Number), y: t.y, type:'scatter', mode:'lines',
    name: t.name, line:{{color:colors[i], width:2}}
  }}));
  const vline = {{x:[0,0], y:[-30,50], type:'scatter', mode:'lines',
    line:{{color:'#555', dash:'dash', width:1}}, showlegend:false}};

  Plotly.newPlot('chart-score', [...traces, vline],
    layout('', {{title:'Minutos desde el gol'}},
               {{title:'Presión (perspectiva del que convierte)'}},
               {{height:380}}), cfg);
}})();

// ─── 6. Equipos ───────────────────────────────────────────────────────────────
(function() {{
  const names = {js(team_names)};
  const doms  = {js(team_pcts)};
  const convs = {js(team_conv)};

  const colors_dom  = doms.map(v => v > 45 ? GREEN : v > 35 ? BLUE : '#3a6080');
  const colors_conv = convs.map(v => v > 60 ? GREEN : v > 45 ? BLUE : ORANGE);

  Plotly.newPlot('chart-teams-dom',
    [{{y:names, x:doms, type:'bar', orientation:'h', marker:{{color:colors_dom}}, name:'% tiempo dominante'}}],
    layout('', {{title:'% tiempo con presión >10'}}, {{automargin:true}}, {{height:380}}), cfg);

  Plotly.newPlot('chart-teams-conv',
    [{{y:names, x:convs, type:'bar', orientation:'h', marker:{{color:colors_conv}}, name:'% goles en momentum'}}],
    layout('', {{title:'% goles convertidos con momentum previo'}}, {{automargin:true}}, {{height:380}}), cfg);
}})();

// ─── 7. Modelo predictivo ────────────────────────────────────────────────────
{pred_js}
</script>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("Cargando datos...")
    raw, form, team_names = load_data()

    print("Construyendo mapa de equipos...")
    team_map = build_team_map(form, raw, team_names)
    mapped = sum(1 for v in team_map.values() if v["home"] or v["away"])
    print(f"  {mapped}/{len(team_map)} partidos con al menos un equipo identificado")

    print("Parseando partidos...")
    matches = [parse_match(eid, mdata, team_map) for eid, mdata in raw.items()]
    print(f"  {len(matches)} partidos procesados")

    total_goals = sum(len(m["goals"]) for m in matches)
    total_reds  = sum(len([c for c in m["cards"] if c["card_type"] in ("red","yellowRed")]) for m in matches)
    print(f"  {total_goals} goles, {total_reds} rojas")

    print("\n--- Análisis 1: Autocorrelación ---")
    ac = analysis_autocorrelation(matches)
    for lag, r in ac.items():
        print(f"  Lag {lag:2d}: AC={r['mean']:.4f}  p={r['p']:.4f}  {'*' if r['p']<0.05 else ''}")

    print("\n--- Análisis 2: Perfil del partido ---")
    profile = analysis_match_profile(matches)
    print(f"  Minutos calculados: {len(profile)}")

    print("\n--- Análisis 3: Triggers ---")
    triggers = analysis_triggers(matches)
    for key, res in triggers.items():
        if res["n"] > 0:
            sig = "**" if res["p_value"] < 0.05 else ""
            print(f"  {key:<22}: n={res['n']:3d}  delta={res['mean_delta']:+.2f}  p={res['p_value']:.4f} {sig}")

    print("\n--- Análisis 4: Duración ---")
    duration = analysis_duration(matches)
    print(f"  N goles: {duration['n_goals']}")
    print(f"  Baseline: {duration['baseline']:.2f}")
    print(f"  Semi-vida: {duration['half_life']} min")

    print("\n--- Análisis 5: Score state ---")
    score_state = analysis_score_state(matches)
    for ctx, res in score_state.items():
        print(f"  {ctx}: n={res['n']}")

    print("\n--- Análisis 6: Teams ---")
    teams = analysis_teams(matches)
    print(f"  Equipos con datos: {len(teams)}")
    for team, s in sorted(teams.items(), key=lambda x: -x[1]['pct_dominant'])[:5]:
        print(f"  {team:<30} dominante={s['pct_dominant']}%  goles_momentum={s['pct_goals_in_momentum']}%")

    print("\n--- Análisis 7: Modelo predictivo ---")
    predictive = analysis_predictive(matches)
    if "auc" in predictive:
        print(f"  N muestras: {predictive['n']}")
        print(f"  AUC: {predictive['auc']:.4f}")
        print(f"  Base rate: {predictive['base_rate']:.3f}")
    else:
        print(f"  Error: {predictive.get('error')}")

    glob = global_stats(matches)

    print("\nGenerando HTML...")
    html = build_html({
        "autocorr":   ac,
        "profile":    profile,
        "triggers":   triggers,
        "duration":   duration,
        "score_state":score_state,
        "teams":      teams,
        "predictive": predictive,
        "global":     glob,
    })

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Listo: {OUT_PATH}")


if __name__ == "__main__":
    main()
