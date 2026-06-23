#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_wc_prediction_model.py — Modelo Dixon-Coles Poisson para predicción de partidos del Mundial 2026

Capas del modelo:
  1. Dixon-Coles: estima alpha_ataque[i] y beta_defensa[i] por equipo usando resultados históricos
     ponderados por calidad del rival (FIFA rank) y tiempo (más reciente = más peso)
  2. Calibración con odds históricas: ajusta los parámetros para minimizar error vs mercado
  3. Patrones temporales: modificador si el equipo tiende a marcar más en 1H o 2H
  4. Situational: modificador de resiliencia (cómo rinde cuando va perdiendo al HT)
  5. Player form: xG esperado del 11 ponderado por p_over60 como multiplicador
  6. Home boost: USA, Canadá, México +15%

Output: wc2026_predictions.json
  {
    "team_params": { team_name: {"alpha": float, "beta": float, "home_adj": float} },
    "fixtures": [
      {
        "event_id": int,
        "home": str, "away": str,
        "lambda_home": float, "lambda_away": float,
        "p_home_win": float, "p_draw": float, "p_away_win": float,
        "ev_home_dt": float,   # EV diferencia de goles para DT local
        "ev_away_dt": float,   # EV diferencia de goles para DT visitante
        "expected_goals_home": float,
        "expected_goals_away": float,
      }
    ]
  }
"""

import json, math, sys, io
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MATCH_ANALYTICS_PATH = Path(__file__).parent / "wc2026_match_analytics.json"
TEAM_STATS_PATH      = Path(__file__).parent / "wc2026_team_stats.json"
PLAYER_STATS_PATH    = Path(__file__).parent / "wc2026_player_stats.json"
SQUADS_PATH          = Path(__file__).parent / "wc2026_squads.json"
FIXTURES_PATH        = Path(__file__).parent / "wc2026_fixtures.json"
ODDS_PATH            = Path(__file__).parent / "wc2026_odds.json"
OUT_PATH             = Path(__file__).parent / "wc2026_predictions.json"

# Equipos con ventaja real de local en el torneo
HOME_BOOST_TEAMS = {"USA", "Canada", "Mexico"}
HOME_BOOST       = 1.15

# FIFA rank → prior de attack/defense si hay pocos datos
FIFA_RANKINGS = {
    # WC 2026 participants
    "Argentina": 100, "France": 95,  "Spain": 92,    "England": 88,
    "Brazil": 85,     "Portugal": 82, "Netherlands": 79, "Belgium": 76,
    "Germany": 74,    "Uruguay": 80,  "Colombia": 68, "Morocco": 65,
    "USA": 62,        "Croatia": 60,  "Switzerland": 58, "Japan": 56,
    "Senegal": 54,    "Mexico": 52,   "South Korea": 50, "Australia": 47,
    "Austria": 45,    "Algeria": 44,  "Norway": 41,   "Czechia": 39,
    "Ecuador": 38,    "Türkiye": 38,  "Saudi Arabia": 38,
    "Iran": 36,       "Canada": 35,   "Cabo Verde": 35,
    "Egypt": 34,      "Scotland": 33, "Tunisia": 31,
    "Iraq": 30,       "DR Congo": 30, "Sweden": 30,
    "Jordan": 28,     "Ghana": 27,    "South Africa": 25,
    "Qatar": 25,      "Panama": 24,   "Paraguay": 23,
    "New Zealand": 20, "Côte d'Ivoire": 45, "Curaçao": 18,
    "Bosnia & Herzegovina": 35, "Uzbekistan": 32, "Haiti": 17,
    # CONMEBOL (frecuentes en clasificatorias)
    "Chile": 47,      "Venezuela": 36, "Peru": 43,    "Bolivia": 21,
    "Colombia": 68,   "Ecuador": 38,   "Uruguay": 80, "Paraguay": 23,
    # UEFA (frecuentes en clasificatorias/amistosos)
    "Italy": 78,      "Denmark": 55,   "Poland": 48,  "Ukraine": 46,
    "Serbia": 44,     "Turkey": 38,    "Greece": 42,  "Romania": 40,
    "Hungary": 37,    "Slovakia": 36,  "Slovenia": 35,"Albania": 33,
    "Georgia": 32,    "Kosovo": 28,    "Montenegro": 27, "Finland": 35,
    "Ireland": 33,    "Wales": 35,     "Luxembourg": 22, "Armenia": 24,
    "Northern Ireland": 26, "Iceland": 32, "Estonia": 22, "Latvia": 20,
    "Lithuania": 20,  "Azerbaijan": 22, "Kazakhstan": 24, "Moldova": 18,
    "Belarus": 26,    "Liechtenstein": 10, "San Marino": 8, "Gibraltar": 9,
    "Faroe Islands": 17, "Andorra": 10, "Cyprus": 24,  "North Macedonia": 28,
    "Israel": 36,     "Bulgaria": 27,  "Malta": 15,   "Kosovo": 28,
    # CAF (Africa - frecuentes en clasificatorias)
    "Nigeria": 48,    "Cameroon": 42,  "Ivory Coast": 45, "Burkina Faso": 30,
    "Mali": 32,       "Zambia": 22,    "Angola": 22,  "Mozambique": 18,
    "Zimbabwe": 20,   "Uganda": 22,    "Tanzania": 19, "Rwanda": 20,
    "Mauritania": 20, "Guinea": 28,    "Kenya": 22,   "Sudan": 18,
    "Benin": 24,      "Congo Republic": 20, "Madagascar": 19, "Togo": 20,
    "Niger": 16,      "Djibouti": 10,  "Eswatini": 14, "Libya": 18,
    "Comoros": 20,    "Botswana": 18,  "Equatorial Guinea": 18,
    "Somalia": 12,    "South Sudan": 12, "Guinea-Bissau": 20,
    # CONCACAF
    "Honduras": 27,   "Costa Rica": 30, "El Salvador": 24, "Guatemala": 22,
    "Trinidad and Tobago": 20, "Jamaica": 25, "Cuba": 17, "Haiti": 17,
    "Suriname": 20,   "Curaçao": 18,  "Bermuda": 14, "Puerto Rico": 12,
    "Nicaragua": 16,  "Dominican Republic": 16, "Belize": 12,
    "Aruba": 10,      "Sint Maarten": 6, "Saint Lucia": 10,
    "Saint Martin": 6, "Grenada": 12,  "Guadeloupe": 14,
    # AFC (Asia)
    "China": 34,      "Indonesia": 28, "Thailand": 28, "Vietnam": 24,
    "Malaysia": 22,   "Bahrain": 26,   "Oman": 26,    "Kuwait": 22,
    "Palestine": 22,  "United Arab Emirates": 28, "Hong Kong": 18,
    "India": 24,      "Kyrgyzstan": 20, "Syria": 24,  "North Korea": 20,
    "Tajikistan": 18, "Myanmar": 16,   "Singapore": 16,
    # OFC
    "New Caledonia": 14, "Fiji": 14,   "Samoa": 10,  "Vanuatu": 12,
    "Tahiti": 12,     "Papua New Guinea": 14,
    # Otros
    "Russia": 40,     "Cote d'Ivoire": 45,
}

LEAGUE_AVG_GOALS = 1.25  # promedio de goles por partido en selecciones (ajustado a histórico Mundial)


def poisson_pmf(k, lam):
    if lam <= 0:
        lam = 0.01
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def match_probs(lam_h, lam_a, max_goals=8):
    """Distribución completa de resultados posibles. Retorna matrices y probabilidades."""
    ph = {k: poisson_pmf(k, lam_h) for k in range(max_goals + 1)}
    pa = {k: poisson_pmf(k, lam_a) for k in range(max_goals + 1)}

    # Dixon-Coles correction para scores bajos (0-0, 1-0, 0-1, 1-1)
    rho = -0.13  # correlación negativa estándar
    def dc_correction(i, j):
        if i == 0 and j == 0:
            return 1 - lam_h * lam_a * rho
        elif i == 1 and j == 0:
            return 1 + lam_a * rho
        elif i == 0 and j == 1:
            return 1 + lam_h * rho
        elif i == 1 and j == 1:
            return 1 - rho
        return 1.0

    p_hw = p_draw = p_aw = 0.0
    ev_home = ev_away = 0.0
    score_dist = {}

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j] * dc_correction(i, j)
            score_dist[(i, j)] = p
            gd = i - j
            if i > j:
                p_hw += p
                ev_home += p * gd
                ev_away += p * gd   # negativo para el visitante
            elif i == j:
                p_draw += p
                # empate → dif = 0, no suma ni resta
            else:
                p_aw += p
                ev_home += p * gd   # negativo para local
                ev_away += p * gd

    # ev_away debe ser desde la perspectiva del equipo visitante
    ev_away_actual = sum(score_dist[(i, j)] * (j - i)
                         for i in range(max_goals + 1)
                         for j in range(max_goals + 1))

    return {
        "p_home_win": round(p_hw, 4),
        "p_draw":     round(p_draw, 4),
        "p_away_win": round(p_aw, 4),
        "ev_home_dt": round(ev_home, 3),
        "ev_away_dt": round(ev_away_actual, 3),
        "score_dist": {f"{i}-{j}": round(p, 4) for (i, j), p in score_dist.items() if p > 0.005},
    }


def odds_to_prob(decimal_odd):
    """Convierte cuota decimal a probabilidad implícita (sin margen)."""
    if not decimal_odd or decimal_odd <= 1:
        return None
    return 1.0 / decimal_odd


def normalize_probs(p1, pd, p2):
    """Elimina el margen de la casa dividiendo por la suma."""
    p1 = p1 or 0
    pd = pd or 0
    p2 = p2 or 0
    total = p1 + pd + p2
    if total <= 0:
        return None, None, None
    return p1 / total, pd / total, p2 / total


def build_team_params(match_analytics, team_stats_raw):
    """
    Calcula alpha (ataque) y beta (defensa) por equipo via Dixon-Coles iterativo.

    Para cada partido, el peso es:
      w = recency_weight × opponent_quality_weight

    recency_weight: exponential decay con half-life de 12 meses
    opponent_quality_weight: sqrt(opponent_fifa / 100) — no penalizar tanto goleadas vs débiles
    """
    import time as time_module

    now_ts = time_module.time()
    HALF_LIFE_SECS = 365 * 24 * 3600  # 12 meses

    # Acumular goles ponderados por equipo
    weighted_gf  = defaultdict(float)
    weighted_gc  = defaultdict(float)
    weight_total = defaultdict(float)

    # También acumular "odds-implied attack" para calibración
    odds_attack   = defaultdict(list)  # lista de (implied_gf, weight)

    # Filtrar minnows sin ranking FIFA real (territorios no-FIFA)
    MIN_OPP_FIFA = 17

    for team_name, tdata in match_analytics.items():
        for m in tdata.get("matches", []):
            score_ft = m.get("score_ft")
            if not score_ft or len(score_ft) < 2:
                continue
            own_gf, own_gc = score_ft[0], score_ft[1]
            # Siempre recalcular opp_fifa desde el dict expandido
            # para corregir defaults incorrectos del scraper
            opp_name = m.get("opponent", "")
            opp_fifa  = FIFA_RANKINGS.get(opp_name) or FIFA_RANKINGS.get(
                opp_name.replace("é","e").replace("ô","o").replace("ü","u"), 18)
            date     = m.get("date") or now_ts

            if opp_fifa < MIN_OPP_FIFA:
                continue

            # opp_strength: escala 0.5 (rival muy débil) → 1.5 (rival de élite)
            # Sirve para normalizar goles por dificultad del rival
            opp_strength = 0.5 + (opp_fifa / 100.0)

            # Cap de goles CRUDOS antes de quality-adjustment para que partidos
            # caóticos (5-3, 6-5) no dominen el average. Un partido con 5+ goles
            # propios no aporta más información de ataque que uno con 4.
            own_gf = min(own_gf, 4)
            own_gc = min(own_gc, 4)

            # Ajuste de goles por calidad del rival:
            #   - Scoring 1 vs Argentina (str=1.5) vale más que scoring 3 vs Bolivia (str=0.65)
            #   - Conceder 1 vs Argentina es menos "malo" que conceder 1 vs Bolivia
            adj_gf = own_gf * opp_strength          # amplifica goles vs fuertes
            adj_gc = own_gc / max(opp_strength, 0.3) # suaviza goles recibidos vs fuertes

            # Cap secundario tras quality-adjustment
            adj_gf = min(adj_gf, 5.0)
            adj_gc = min(adj_gc, 5.0)

            # Peso temporal: half-life de 12 meses
            age_secs   = max(0, now_ts - date)
            rec_weight = math.exp(-0.693 * age_secs / HALF_LIFE_SECS)

            # Peso de partido: mayor cuanto más fuerte el rival (partidos vs élite pesan más)
            # Para partidos del Mundial: el descuento por rival débil es menor.
            # Razón: en el Mundial todos los rivales clasificaron; además el contexto
            # es de máxima presión, por lo que 1.13 xG vs Haití sí dice algo del ataque.
            is_wc = m.get("_wc_match", False)
            opp_exp = 0.3 if is_wc else 0.6   # WC: penaliza menos por rival débil → más señal
            opp_weight = (opp_fifa / 100.0) ** opp_exp

            w = rec_weight * opp_weight
            weighted_gf[team_name]  += adj_gf * w
            weighted_gc[team_name]  += adj_gc * w
            weight_total[team_name] += w

            # Calibración desde odds
            odds = m.get("odds_1x2")
            if odds and odds.get("home") and odds.get("draw") and odds.get("away"):
                is_home = m.get("is_home", True)
                ph  = odds_to_prob(odds["home"])
                pd  = odds_to_prob(odds["draw"])
                paw = odds_to_prob(odds["away"])
                ph_norm, pd_norm, paw_norm = normalize_probs(ph, pd, paw)
                if ph_norm:
                    # El mercado implica lambda para el local
                    # Proxy simple: lambda_home ≈ -log(P(0 goles home)) → resolver de P(draw) ≈ exp(-lh)*exp(-la)
                    p_win = ph_norm if is_home else paw_norm
                    # implied_lambda ≈ -log(1 - p_win) × 1.5 (heurística)
                    impl_lam = max(0.3, min(4.0, -math.log(max(1 - p_win, 0.01)) * 1.8))
                    odds_attack[team_name].append((impl_lam, w))

    # Construir parámetros alpha/beta
    league_avg_gf = (sum(weighted_gf.values()) / max(sum(weight_total.values()), 0.01))
    league_avg_gc = league_avg_gf  # simétrico

    params = {}
    for team_name in set(list(weighted_gf.keys())) | set(team_stats_raw.keys()):
        ts  = team_stats_raw.get(team_name, {})
        fifa = FIFA_RANKINGS.get(team_name, 40)

        # Alpha = ataque relativo (1.0 = promedio liga)
        if weight_total[team_name] > 0:
            raw_alpha = (weighted_gf[team_name] / weight_total[team_name]) / max(league_avg_gf, 0.01)
        else:
            # Sin datos: usar FIFA rank como proxy (top team debería atacar ~20% sobre media)
            raw_alpha = 0.7 + (fifa / 100.0) * 0.6

        # Beta = defensa (menor = mejor. 1.0 = promedio, <1 = buena defensa)
        if weight_total[team_name] > 0:
            raw_beta = (weighted_gc[team_name] / weight_total[team_name]) / max(league_avg_gc, 0.01)
        else:
            raw_beta = 1.3 - (fifa / 100.0) * 0.6

        # Blend con prior FIFA (regresión a la media para equipos con pocos datos)
        n_matches = weight_total[team_name]
        blend_w   = min(1.0, n_matches / 8.0)  # a partir de 8 partidos ponderados = confiar 100%
        prior_alpha = 0.7 + (fifa / 100.0) * 0.6
        prior_beta  = 1.3 - (fifa / 100.0) * 0.6

        alpha = raw_alpha * blend_w + prior_alpha * (1 - blend_w)
        beta  = max(0.2, raw_beta * blend_w + prior_beta * (1 - blend_w))

        # Calibración con odds si disponible
        if odds_attack[team_name]:
            impl_lams = [lam for lam, _ in odds_attack[team_name]]
            weights   = [w for _, w in odds_attack[team_name]]
            implied_alpha = sum(l * w for l, w in zip(impl_lams, weights)) / max(sum(weights), 0.01)
            implied_alpha /= max(league_avg_gf, 0.01)
            odds_w  = min(0.4, len(odds_attack[team_name]) / 20 * 0.4)
            alpha   = alpha * (1 - odds_w) + implied_alpha * odds_w

        params[team_name] = {
            "alpha":     round(alpha, 4),
            "beta":      round(max(0.2, beta), 4),
            "n_matches": round(weight_total[team_name], 2),
            "fifa":      fifa,
        }

    return params, league_avg_gf


def build_period_patterns(match_analytics):
    """
    Calcula para cada equipo:
      - ratio_1h: fracción de sus goles marcados en 1H vs total
      - ratio_1h_conceded: fracción de goles recibidos en 1H
      - resilience: % de partidos que van abajo al HT y empatan o ganan
    """
    patterns = {}
    for team_name, tdata in match_analytics.items():
        gf_1h = gf_2h = gc_1h = gc_2h = 0
        trailing_ht = came_back = 0

        for m in tdata.get("matches", []):
            ft = m.get("score_ft")
            ht = m.get("score_ht")
            if not ft or len(ft) < 2:
                continue
            own_ft, opp_ft = ft[0], ft[1]
            gd_ft = own_ft - opp_ft

            # Patrones temporales desde stats de periodo
            stats = m.get("stats", {})
            is_home = m.get("is_home", True)
            side = "home" if is_home else "away"

            for period, pstats in stats.items():
                bc = (pstats.get("Big chances scored") or {}).get(side)
                shots = (pstats.get("Shots on target") or {}).get(side)
                if period == "1ST":
                    if bc is not None:
                        gf_1h += bc
                    elif shots is not None:
                        gf_1h += shots * 0.3  # proxy
                elif period == "2ND":
                    if bc is not None:
                        gf_2h += bc
                    elif shots is not None:
                        gf_2h += shots * 0.3

            # Resilience desde HT score
            if ht and len(ht) == 2:
                own_ht, opp_ht = ht[0], ht[1]
                if own_ht < opp_ht:   # van perdiendo al HT
                    trailing_ht += 1
                    if own_ft >= opp_ft:  # empatan o ganan al final
                        came_back += 1

        total_1h = gf_1h + gf_2h
        ratio_1h = (gf_1h / total_1h) if total_1h > 0 else 0.5
        resilience = (came_back / trailing_ht) if trailing_ht >= 3 else 0.33

        patterns[team_name] = {
            "ratio_goals_1h":  round(ratio_1h, 3),
            "resilience":      round(resilience, 3),
            "trailing_ht_n":   trailing_ht,
        }

    return patterns


def build_player_form(player_stats, squads):
    """
    Calcula ataque esperado por equipo sumando xG/90 de los jugadores
    con alta probabilidad de jugar (p_over60 usada como proxy de minutos).
    """
    form = {}

    for team_name, tdata in squads.items():
        player_ids = {str(p["id"]) for p in tdata.get("players", [])}
        team_players = [
            v for k, v in player_stats.items()
            if str(k) in player_ids or v.get("national_team") == team_name
        ]
        if not team_players:
            form[team_name] = 1.0
            continue

        xg_sum = 0.0
        for p in team_players:
            pos = p.get("position", "M")
            if pos == "G":
                continue  # arqueros no cuentan para ataque
            ist = p.get("intl_stats") or {}
            mins = ist.get("Minutos Jugados") or 0
            pj   = ist.get("Partidos Jugados") or 0
            xg   = ist.get("xG") or 0.0
            if mins > 0:
                xg_per90 = xg / mins * 90
                # Proxy de p_over60 desde minutos
                avg_mins = mins / max(pj, 1)
                if pos == "D":
                    p60 = min(0.92, max(0.10, (avg_mins - 10) / 70))
                elif pos == "M":
                    p60 = min(0.90, max(0.05, (avg_mins - 20) / 65))
                else:
                    p60 = min(0.88, max(0.05, (avg_mins - 25) / 60))
                xg_sum += xg_per90 * p60

        # Normalizar: el promedio de xG/partido debería ser ~1.2 goles
        # xg_sum es la suma ponderada de todos los jugadores
        form[team_name] = round(xg_sum, 3)

    # Normalizar a ratio sobre la media
    vals = [v for v in form.values() if v > 0]
    if vals:
        avg_form = sum(vals) / len(vals)
        form = {k: round(v / avg_form, 4) if avg_form > 0 else 1.0 for k, v in form.items()}

    return form


def main():
    print("Cargando datos...")

    match_analytics = {}
    if MATCH_ANALYTICS_PATH.exists():
        match_analytics = json.load(open(MATCH_ANALYTICS_PATH, encoding="utf-8"))
        print(f"  match_analytics: {len(match_analytics)} equipos")

    team_stats_raw = json.load(open(TEAM_STATS_PATH, encoding="utf-8"))
    player_stats   = json.load(open(PLAYER_STATS_PATH, encoding="utf-8"))
    squads         = json.load(open(SQUADS_PATH, encoding="utf-8"))
    fixtures_raw   = json.load(open(FIXTURES_PATH, encoding="utf-8"))
    fixtures       = fixtures_raw.get("fixtures", [])

    # Cuotas reales del mercado (The Odds API) — indexadas por event_id
    market_odds = {}
    if ODDS_PATH.exists():
        raw_odds = json.load(open(ODDS_PATH, encoding="utf-8"))
        for k, v in raw_odds.items():
            eid = v.get("event_id")
            if eid:
                market_odds[eid] = v.get("odds_1x2")
        print(f"  market_odds: {len(market_odds)} partidos")

    print(f"  team_stats: {len(team_stats_raw)} equipos")
    print(f"  player_stats: {len(player_stats)} jugadores")
    print(f"  fixtures: {len(fixtures)} partidos\n")

    # 1. Parámetros Dixon-Coles
    print("Estimando parámetros Dixon-Coles...")
    team_params, league_avg = build_team_params(match_analytics, team_stats_raw)
    print(f"  league_avg_goals: {league_avg:.3f}")

    # 2. Patrones temporales y resilience
    print("Calculando patrones temporales...")
    patterns = build_period_patterns(match_analytics)

    # 3. Player form
    print("Calculando player form...")
    player_form = build_player_form(player_stats, squads)

    # 4. Predicciones por partido
    print("Generando predicciones...")
    fixture_preds = []

    for fix in fixtures:
        home = fix.get("home_name") or fix.get("home")
        away = fix.get("away_name") or fix.get("away")
        eid  = fix.get("event_id") or fix.get("id")
        if not home or not away:
            continue

        ph = team_params.get(home, {"alpha": 1.0, "beta": 1.0})
        pa = team_params.get(away, {"alpha": 1.0, "beta": 1.0})

        # λ base: ataque_local × defensa_rival × promedio_liga
        lam_h = ph["alpha"] * pa["beta"] * league_avg
        lam_a = pa["alpha"] * ph["beta"] * league_avg

        # Home boost
        if home in HOME_BOOST_TEAMS:
            lam_h *= HOME_BOOST
            lam_a /= (HOME_BOOST ** 0.5)
        elif away in HOME_BOOST_TEAMS:
            lam_a *= HOME_BOOST
            lam_h /= (HOME_BOOST ** 0.5)

        # Player form multiplier (suavizado para no amplificar en exceso)
        form_h = player_form.get(home, 1.0)
        form_a = player_form.get(away, 1.0)
        lam_h *= (0.7 + 0.3 * form_h)
        lam_a *= (0.7 + 0.3 * form_a)

        lam_h = max(0.2, min(5.0, lam_h))
        lam_a = max(0.2, min(5.0, lam_a))

        # Calibración con cuotas del mercado (The Odds API)
        mkt = market_odds.get(eid)
        mkt_applied = False
        if mkt and all(v and v > 1.0 for v in [mkt.get("home"), mkt.get("draw"), mkt.get("away")]):
            raw_h = 1.0 / mkt["home"]
            raw_d = 1.0 / mkt["draw"]
            raw_a = 1.0 / mkt["away"]
            vig = raw_h + raw_d + raw_a
            mkt_ph = raw_h / vig

            # Bisección para hallar r = lam_h_mkt/lam_a_mkt que reproduce mkt_ph
            total = lam_h + lam_a
            lo_r, hi_r = 0.05, 20.0
            for _ in range(25):
                mid_r = (lo_r + hi_r) / 2.0
                lh_t = total * mid_r / (1.0 + mid_r)
                la_t = total / (1.0 + mid_r)
                if match_probs(lh_t, la_t)["p_home_win"] > mkt_ph:
                    hi_r = mid_r
                else:
                    lo_r = mid_r
            r_mkt = (lo_r + hi_r) / 2.0
            lam_h_mkt = total * r_mkt / (1.0 + r_mkt)
            lam_a_mkt = total / (1.0 + r_mkt)

            MKT_W = 0.6
            lam_h = lam_h * (1.0 - MKT_W) + lam_h_mkt * MKT_W
            lam_a = lam_a * (1.0 - MKT_W) + lam_a_mkt * MKT_W
            mkt_applied = True

        lam_h = round(max(0.2, min(5.0, lam_h)), 4)
        lam_a = round(max(0.2, min(5.0, lam_a)), 4)

        probs = match_probs(lam_h, lam_a)

        fixture_preds.append({
            "event_id":       eid,
            "round":          fix.get("round_num"),
            "group":          fix.get("group"),
            "home":           home,
            "away":           away,
            "lambda_home":    lam_h,
            "lambda_away":    lam_a,
            "p_home_win":     probs["p_home_win"],
            "p_draw":         probs["p_draw"],
            "p_away_win":     probs["p_away_win"],
            "ev_home_dt":     probs["ev_home_dt"],
            "ev_away_dt":     probs["ev_away_dt"],
            "score_dist":     probs["score_dist"],
            "home_form":      round(form_h, 3),
            "away_form":      round(form_a, 3),
            "mkt_calibrated": mkt_applied,
            "mkt_odds":       mkt if mkt_applied else None,
        })

    # Imprimir tabla de parámetros
    print("\nParámetros por equipo (alpha=ataque, beta=defensa):")
    for name, p in sorted(team_params.items(), key=lambda x: -x[1]["alpha"]):
        print(f"  {name:<25} α={p['alpha']:.3f}  β={p['beta']:.3f}  n={p['n_matches']:.1f}")

    print("\nTop 10 DTs por EV (diferencia de goles esperada):")
    phase1 = [f for f in fixture_preds if f.get("round") == 1]
    all_dt = []
    for f in phase1:
        all_dt.append({"team": f["home"], "opp": f["away"],  "ev": f["ev_home_dt"], "lam": f["lambda_home"]})
        all_dt.append({"team": f["away"], "opp": f["home"],  "ev": f["ev_away_dt"], "lam": f["lambda_away"]})
    for d in sorted(all_dt, key=lambda x: -x["ev"])[:10]:
        sign = "+" if d["ev"] >= 0 else ""
        print(f"  {d['team']:<25} vs {d['opp']:<25} EV={sign}{d['ev']:.3f}  λ={d['lam']:.2f}")

    # Guardar
    output = {
        "team_params":    team_params,
        "period_patterns": patterns,
        "player_form":    player_form,
        "league_avg":     round(league_avg, 4),
        "fixtures":       fixture_preds,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado: {OUT_PATH}")


if __name__ == "__main__":
    main()
