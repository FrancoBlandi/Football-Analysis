#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_dc_with_f1.py — Inyecta los resultados de fecha 1 en match_analytics
y recorre build_wc_prediction_model.py para actualizar las predicciones.

Los partidos del Mundial tienen:
  - Peso extra (WORLD_CUP_WEIGHT) por ser partidos de máxima competencia
  - Timestamp actual para que el decay temporal los ponga al tope
"""
import json, subprocess, sys, io, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR            = Path(__file__).parent
WC_RESULTS_PATH     = BASE_DIR / "wc2026_wc_results.json"
MATCH_ANALYTICS_PATH = BASE_DIR / "wc2026_match_analytics.json"
TEAM_STATS_PATH     = BASE_DIR / "wc2026_team_stats.json"
FIXTURES_PATH       = BASE_DIR / "wc2026_fixtures.json"

WORLD_CUP_WEIGHT_F1 = 8   # F1: más reciente y de máxima presión, pero aún sample chico
WORLD_CUP_WEIGHT_F2 = 12  # F2: más info acumulada sobre el torneo, actualiza más fuerte
WORLD_CUP_WEIGHT    = WORLD_CUP_WEIGHT_F1  # compat (no usado directamente abajo)


def main():
    wc_results  = json.load(open(WC_RESULTS_PATH, encoding="utf-8"))
    match_analytics = json.load(open(MATCH_ANALYTICS_PATH, encoding="utf-8"))
    team_stats  = json.load(open(TEAM_STATS_PATH, encoding="utf-8"))

    # Timestamp actual (para que sean los más recientes en el decay)
    import time as t
    now_ts = int(t.time())

    # FIFA rank de cada equipo desde team_stats
    fifa_rank = {name: d.get("fifa_rank_score", 40) for name, d in team_stats.items()}

    added_matches = 0
    wc_eids_added = set()  # evitar duplicados

    for eid_str, md in wc_results.get("matches", {}).items():
        if md.get("round_num") not in (1, 2):
            continue

        eid     = int(eid_str)
        home_nm = md["home"]
        away_nm = md["away"]
        sh      = md.get("score_home")
        sa      = md.get("score_away")

        if sh is None or sa is None:
            continue

        round_num = md.get("round_num", 1)
        wc_weight = WORLD_CUP_WEIGHT_F2 if round_num == 2 else WORLD_CUP_WEIGHT_F1

        # ── xG de equipo sumando stats de jugadores ───────────────────────────
        xg_h, xg_a = 0.0, 0.0
        for pst in md.get("player_stats", {}).values():
            xg = pst.get("xg") or 0.0
            if pst.get("is_home"):
                xg_h += xg
            else:
                xg_a += xg

        # Blend 80% xG + 20% goles: en un solo partido el xG es más señal que los goles.
        # Un equipo que genera 1.0 xG y no convierte no debería ser penalizado igual
        # que uno que no generó nada. Los goles tienen alta varianza en muestras pequeñas.
        eff_h = round(0.8 * xg_h + 0.2 * sh, 3) if xg_h > 0 else sh
        eff_a = round(0.8 * xg_a + 0.2 * sa, 3) if xg_a > 0 else sa

        # Shots para estadísticas complementarias
        zone_home = md.get("zones", {}).get(str(md["home_id"]), {})
        zone_away = md.get("zones", {}).get(str(md["away_id"]), {})
        shots_h = zone_home.get("total_shots", 10)
        shots_a = zone_away.get("total_shots", 10)

        def build_match_entry(own_eff, opp_eff, is_home, opp_name, own_shots, opp_shots):
            """Construye una entrada de partido en formato match_analytics.
            own_eff / opp_eff = blend(xG, goles) — mejor señal que goles solos."""
            opp_fifa = fifa_rank.get(opp_name, 40)
            return {
                "event_id":      eid,
                "is_home":       is_home,
                "opponent":      opp_name,
                "opponent_fifa": opp_fifa,
                "date":          now_ts,
                "score_ft":      [own_eff, opp_eff],
                "score_ht":      None,
                "stats": {
                    "ALL": {
                        "Total shots":      {"home": own_shots if is_home else opp_shots,
                                             "away": opp_shots if is_home else own_shots},
                        "Ball possession":  {"home": None, "away": None},
                        "Shots on target":  {"home": None, "away": None},
                    }
                },
                "odds_1x2":   None,
                "odds_ou":    None,
                "odds_btts":  None,
                "_wc_match":  True,
                "_round_num": round_num,
                "_weight":    wc_weight,
            }

        for team_name, own_eff, opp_eff, is_home, own_shots in [
            (home_nm, eff_h, eff_a, True,  shots_h),
            (away_nm, eff_a, eff_h, False, shots_a),
        ]:
            if team_name not in match_analytics:
                match_analytics[team_name] = {
                    "team_id": md["home_id"] if team_name == home_nm else md["away_id"],
                    "group":   md.get("group", ""),
                    "matches": [],
                }

            entry = build_match_entry(own_eff, opp_eff, is_home,
                                      away_nm if team_name == home_nm else home_nm,
                                      own_shots, shots_h if team_name == away_nm else shots_a)

            # Evitar duplicados
            existing_eids = {m.get("event_id") for m in match_analytics[team_name]["matches"]}
            if eid not in existing_eids:
                # Insertar al inicio (más reciente primero)
                match_analytics[team_name]["matches"].insert(0, entry)
                # Agregar repetido para simular el peso extra
                for _ in range(wc_weight - 1):
                    match_analytics[team_name]["matches"].insert(0, {**entry, "_weight_copy": True})
                added_matches += 1

    print(f"Partidos WC F1 inyectados: {added_matches}")

    # Guardar match_analytics actualizado
    backup_path = MATCH_ANALYTICS_PATH.with_suffix(".backup_pre_f1.json")
    if not backup_path.exists():
        json.dump(json.load(open(MATCH_ANALYTICS_PATH, encoding="utf-8")),
                  open(backup_path, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"Backup: {backup_path}")

    json.dump(match_analytics, open(MATCH_ANALYTICS_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"match_analytics actualizado: {MATCH_ANALYTICS_PATH}")

    # Reconstruir predicciones
    print("\nReconstruyendo modelo Dixon-Coles...")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "build_wc_prediction_model.py")],
        capture_output=True, text=True, cwd=str(BASE_DIR)
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-20:]:
            print(" ", line)
    if result.returncode != 0:
        print("ERROR:", result.stderr[-500:] if result.stderr else "sin detalle")
        return
    print("Predicciones actualizadas.")

    # ── Capa WC Form: ajuste post-DC basado en xG real del Mundial ──────────
    # El modelo DC calibra bien el histórico pero suaviza demasiado un solo partido WC.
    # Esta capa aplica un multiplicador directo sobre lambda_home/lambda_away en
    # predictions.json basado en la performance xG de cada equipo en F1.
    #
    # wc_form_ratio[team] = adj_gf_wc / avg_adj_gf_liga
    #   adj_gf_wc = xG_efectivo × opp_strength (mismo ajuste que DC)
    #   avg_adj_gf_liga ≈ 1.0 (normalizado)
    # Rango: [0.5, 1.5] — no mover más del 50% el lambda base.
    print("\nAplicando capa WC Form sobre lambdas...")

    FIFA_WC = {name: d.get("fifa_rank_score", 40) for name, d in team_stats.items()}
    FIFA_WC.update({   # ranks de equipos no en WC que aparecen en match_analytics
        "Haiti": 17, "Curaçao": 18,
    })

    LEAGUE_AVG_ADJ_GF = 1.05   # promedio mundial de adj_gf en partidos WC (estimado)
    WC_FORM_WEIGHT    = 0.35   # cuánto pesa el WC form vs el DC base (0 = ignorar, 1 = reemplazar)
    WC_FORM_CAP       = (0.60, 1.45)  # cap del multiplicador final

    # Calcular adj_gf WC por equipo — F1 y F2 (promedio si hay varios)
    wc_adj_gf_sum   = {}
    wc_adj_gf_count = {}
    wc_adj_gf       = {}
    for eid_str, md in wc_results.get("matches", {}).items():
        if md.get("round_num") not in (1, 2):
            continue
        for team_nm, is_h in [(md["home"], True), (md["away"], False)]:
            opp_nm  = md["away"] if is_h else md["home"]
            opp_f   = FIFA_WC.get(opp_nm, 30)
            opp_str = 0.5 + opp_f / 100.0
            xg_team = sum(
                (p.get("xg") or 0) for p in md["player_stats"].values()
                if p.get("is_home") == is_h
            )
            sc     = md.get("score_home" if is_h else "score_away") or 0
            eff    = 0.8 * xg_team + 0.2 * sc
            adj_gf = min(eff * opp_str, 5.0)
            # Promedio ponderado: F2 pesa 2.0x vs F1 (más datos, más señal)
            rnd_w  = 2.0 if md.get("round_num") == 2 else 1.0
            wc_adj_gf_sum[team_nm]   = wc_adj_gf_sum.get(team_nm, 0) + adj_gf * rnd_w
            wc_adj_gf_count[team_nm] = wc_adj_gf_count.get(team_nm, 0) + rnd_w

    for team_nm in wc_adj_gf_sum:
        wc_adj_gf[team_nm] = wc_adj_gf_sum[team_nm] / wc_adj_gf_count[team_nm]

    # Aplicar sobre predictions.json
    pred = json.load(open(BASE_DIR / "wc2026_predictions.json", encoding="utf-8"))
    adjusted = 0
    for fx in pred.get("fixtures", []):
        if fx.get("round", 1) == 1:
            continue   # F1 ya jugado, no tocar
        home_nm = fx.get("home", "")
        away_nm = fx.get("away", "")
        for side, opp in [("home", away_nm), ("away", home_nm)]:
            team = home_nm if side == "home" else away_nm
            if team not in wc_adj_gf:
                continue
            adj_gf = wc_adj_gf[team]
            form_ratio = adj_gf / LEAGUE_AVG_ADJ_GF
            # Multiplicador: blend entre 1.0 (sin cambio) y form_ratio
            mult = 1.0 * (1 - WC_FORM_WEIGHT) + form_ratio * WC_FORM_WEIGHT
            mult = max(WC_FORM_CAP[0], min(WC_FORM_CAP[1], mult))
            key  = f"lambda_{side}"
            if key in fx:
                fx[key] = round(fx[key] * mult, 4)
                adjusted += 1

    json.dump(pred, open(BASE_DIR / "wc2026_predictions.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"  {adjusted} lambdas ajustados por WC form")

    # Verificar casos clave
    import math as _math
    check = [("Scotland","Morocco"), ("Haiti","Brazil"), ("Spain","Saudi Arabia"), ("Switzerland","Qatar")]
    for att, def_ in check:
        for fx in pred["fixtures"]:
            h, a = fx.get("home",""), fx.get("away","")
            if att.lower() in h.lower() or att.lower() in a.lower():
                if def_.lower() in h.lower() or def_.lower() in a.lower():
                    lh, la = fx["lambda_home"], fx["lambda_away"]
                    att_lam = la if def_.lower() in h.lower() else lh
                    print(f"  {att:<18} vs {def_:<14} lam={att_lam:.3f}  p_cs={_math.exp(-att_lam)*100:.1f}%")
                    break


if __name__ == "__main__":
    main()
