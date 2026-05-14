"""
aplicar_correcciones_finales.py — Aplica todas las correcciones de goles verificadas por prensa
y recalcula ratings via regresión Ridge.

Fuentes:
  Copelotti/Paz   → ESPN Uruguay
  Renato César    → ESPN Uruguay / La Diaria (J3 Peñarol vs Maldonado)
  Ginella         → Tenfield / Montevideo Portal (J5 Progreso vs Albion)
  Fracchia/Marcel → Montevideo Portal / AUF TV (J9 Cerro Largo vs Danubio)
"""

import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Correcciones verificadas por prensa ──────────────────────────────────────
# Formato: (event_id, player_id, nombre, delta_goals, fuente)
CORRECCIONES = [
    # J3 Peñarol 2-1 Maldonado
    (15523837, 248023,  "Renato César",        -1, "ESPN Uruguay / La Diaria — no anotó (anotó Juan Ramos)"),
    (15523837, 587824,  "Juan Ramos",          +1, "ESPN Uruguay / La Diaria — gol min ~32"),

    # J5 Progreso 2-2 Albion
    (15634213, 922999,  "Francisco Ginella",   +1, "Tenfield / Montevideo Portal — gol min 54, tiro libre"),

    # J9 Cerro Largo 2-0 Danubio
    (15713283, 889504,  "Matías Fracchia",     -1, "Montevideo Portal / AUF TV — no anotó; gol atribuido al equipo equivocado"),
    (15713283, 1512465, "Santiago Marcel",     +1, "Montevideo Portal / AUF TV — gol min ~38"),

    # J9 Progreso 3-3 Liverpool
    (15907398, 2059740, "Nicolás Agustín Paz", -1, "ESPN Uruguay — gol del min 40 era de Copelotti, no de Paz"),
    (15907398, 1643434, "Matteo Copelotti",    +1, "ESPN Uruguay — gol min 21 + gol min 40"),
]

# ── Correcciones SIN impacto en rating (lineups ya correcto) ────────────────
SIN_IMPACTO_RATING = [
    "J12 Racing 1-1 Defensor: Habib=1 gol y Montenegro=1 gol ya en lineups (solo incidents estaba mal)",
    "J13 Cerro Largo 0-1 Racing: Cotugno=1 gol ya en lineups",
    "J15 Wanderers 1-0 Liverpool: Zeballos=1 gol ya en lineups",
]

FEATURES = [
    "minutesPlayed", "goals", "assists", "yellowCards", "redCards",
    "tackles", "interceptions", "clearances", "keyPasses", "successfulDribbles",
    "accuratePasses", "totalPasses", "shotsOnTarget", "shotsOffTarget",
    "bigChancesCreated", "bigChancesMissed", "aerialDuelsWon", "aerialLost",
    "touches", "ballRecovery", "fouls", "wasFouled", "dispossessed",
    "saves", "goalsConceded",
]
POS_MAP = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}


def train_models(dataset_rows):
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score

    models = {}
    grupos = {"TODOS": dataset_rows}
    for g in ["GK", "DEF", "MID", "FWD"]:
        sub = [r for r in dataset_rows if r.get("grupo") == g]
        if len(sub) >= 20:
            grupos[g] = sub

    for label, rows in grupos.items():
        X = [[r.get(f, 0) or 0 for f in FEATURES] for r in rows]
        y = [r["rating"] for r in rows]
        import numpy as np
        X, y = np.array(X, dtype=float), np.array(y, dtype=float)
        sc = __import__("sklearn.preprocessing", fromlist=["StandardScaler"]).StandardScaler()
        X_sc = sc.fit_transform(X)
        m = Ridge(alpha=1.0).fit(X_sc, y)
        models[label] = {"model": m, "scaler": sc, "r2": r2_score(y, m.predict(X_sc))}

    return models


def predict(model_info, stats_dict):
    import numpy as np
    x = np.array([[stats_dict.get(f, 0) or 0 for f in FEATURES]], dtype=float)
    return float(model_info["model"].predict(model_info["scaler"].transform(x))[0])


def main():
    from sklearn.linear_model import Ridge

    with open("apertura2026_dataset_ratings.json", encoding="utf-8") as f:
        dataset = json.load(f)

    # Agregar campo grupo
    for r in dataset:
        r["grupo"] = POS_MAP.get(r.get("posicion", ""), "UNK") if "posicion" in r else r.get("grupo", "UNK")

    print("Entrenando modelos por posición...")
    models = train_models([r for r in dataset if r.get("rating")])
    for g, m in models.items():
        print(f"  {g}: R²={m['r2']:.3f}")

    row_by_key = {(r["event_id"], r["player_id"]): r for r in dataset}

    print(f"\n{'='*70}")
    print("CORRECCIONES DE RATING VERIFICADAS POR PRENSA")
    print(f"{'Jugador':<30} {'Partido':>8} {'Goles orig':>10} {'Goles corr':>10} {'Rating orig':>11} {'Rating corr':>11} {'Delta':>6}")
    print("-" * 90)

    resultado = []
    for ev_id, pid, nombre, delta, fuente in CORRECCIONES:
        key = (ev_id, pid)
        row = row_by_key.get(key)
        if not row:
            print(f"  {nombre:<30} ev={ev_id} — SIN DATOS en dataset")
            resultado.append({"nombre": nombre, "event_id": ev_id, "player_id": pid,
                               "delta_goals": delta, "fuente": fuente,
                               "error": "sin datos en dataset"})
            continue

        rating_orig  = row["rating"]
        goals_orig   = row.get("goals", 0) or 0
        goals_corr   = max(0, goals_orig + delta)
        grupo        = row.get("grupo", "TODOS")
        model_info   = models.get(grupo) or models.get("TODOS")

        stats_corr = dict(row)
        stats_corr["goals"] = goals_corr
        rating_corr = round(max(1.0, min(10.0, predict(model_info, stats_corr))), 2)
        d_rating    = round(rating_corr - rating_orig, 2)

        print(f"  {nombre:<30} ev={ev_id} {goals_orig:>10} {goals_corr:>10} {rating_orig:>11.2f} {rating_corr:>11.2f} {d_rating:>+6.2f}")

        resultado.append({
            "nombre":       nombre,
            "player_id":    pid,
            "event_id":     ev_id,
            "grupo":        grupo,
            "delta_goals":  delta,
            "goals_orig":   goals_orig,
            "goals_corr":   goals_corr,
            "rating_orig":  rating_orig,
            "rating_corr":  rating_corr,
            "delta_rating": d_rating,
            "fuente":       fuente,
        })

    print(f"\nNota — sin impacto en rating (lineups ya era correcto):")
    for nota in SIN_IMPACTO_RATING:
        print(f"  • {nota}")

    out = {
        "fecha": __import__("datetime").date.today().isoformat(),
        "modelos_r2": {k: round(v["r2"], 3) for k, v in models.items()},
        "correcciones": resultado,
        "sin_impacto_rating": SIN_IMPACTO_RATING,
    }
    with open("apertura2026_correcciones_finales.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nGuardado en apertura2026_correcciones_finales.json")


if __name__ == "__main__":
    main()
