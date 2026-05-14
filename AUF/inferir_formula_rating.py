"""
inferir_formula_rating.py — Intenta inferir la fórmula de rating de SofaScore
mediante regresión lineal sobre las estadísticas por partido de los jugadores
del Apertura 2026 (Liga AUF Uruguaya).

Pasos:
  1. Fetch lineups completos de todos los partidos del Apertura 2026
  2. Arma dataset: una fila por jugador/partido con stats + rating
  3. Regresión OLS por posición (GK / DEF / MID / FWD)
  4. Reporta coeficientes, R², y aplica corrección a jugadores afectados

Requiere:
    pip install scikit-learn numpy
"""

import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TOURNAMENT_ID = 278

# Stats que SofaScore expone en lineups y que son candidatos a entrar en el rating
STAT_FIELDS = [
    "minutesPlayed",
    "goals", "assists",
    "yellowCards", "redCards",
    "tackles", "interceptions", "clearances",
    "keyPasses", "successfulDribbles", "totalContest",
    "accuratePasses", "totalPasses",
    "accurateLongBalls", "totalLongBalls",
    "accurateCrosses", "totalCross",
    "shotsOnTarget", "shotsOffTarget",
    "bigChancesCreated", "bigChancesMissed",
    "aerialDuelsWon", "aerialLost",
    "groundDuelsWon", "duelLost",
    "wasFouled", "fouls",
    "dispossessed", "possessionLost",
    "touches", "ballRecovery",
    "savedShotsFromInsideTheBox", "saves", "punches",  # porteros
    "goalsConceded", "errorLeadToAShot",
]

# Posiciones SofaScore → grupo
POSITION_MAP = {
    "G": "GK",
    "D": "DEF",
    "M": "MID",
    "F": "FWD",
}


def fetch_json(page, url):
    result = page.evaluate(f"""
        async () => {{
            try {{
                const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
                if (!resp.ok) return {{"_status": resp.status}};
                return await resp.json();
            }} catch(e) {{
                return {{"_error": e.toString()}};
            }}
        }}
    """)
    return result or {}


def fetch_lineups_stats(page, event_id):
    """Devuelve lista de dicts con stats + rating por jugador del partido."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    data = fetch_json(page, url)
    rows = []
    for side in ["home", "away"]:
        for entry in data.get(side, {}).get("players", []):
            p     = entry.get("player", {})
            stats = entry.get("statistics") or {}
            rating = stats.get("rating")
            if rating is None:
                continue  # sin rating → no sirve para entrenar
            pid = p.get("id")
            pos = p.get("position", "")
            row = {
                "player_id": pid,
                "nombre":    p.get("name", ""),
                "event_id":  event_id,
                "posicion":  pos,
                "grupo":     POSITION_MAP.get(pos, "UNK"),
                "rating":    rating,
            }
            for f in STAT_FIELDS:
                row[f] = stats.get(f) or 0
            rows.append(row)
    return rows


def collect_dataset(page, event_ids):
    all_rows = []
    for i, ev_id in enumerate(event_ids, 1):
        rows = fetch_lineups_stats(page, ev_id)
        all_rows.extend(rows)
        if i % 10 == 0:
            print(f"  Partido {i}/{len(event_ids)} — filas acumuladas: {len(all_rows)}")
        page.wait_for_timeout(120)
    return all_rows


def run_regression(rows, grupo_label="TODOS"):
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score

    # Features candidatos (excluir minutesPlayed como predictor directo,
    # pero incluir para controlar por tiempo en cancha)
    FEATURES = [
        "minutesPlayed",
        "goals", "assists",
        "yellowCards", "redCards",
        "tackles", "interceptions", "clearances",
        "keyPasses", "successfulDribbles",
        "accuratePasses", "totalPasses",
        "shotsOnTarget", "shotsOffTarget",
        "bigChancesCreated", "bigChancesMissed",
        "aerialDuelsWon", "aerialLost",
        "touches", "ballRecovery",
        "fouls", "wasFouled", "dispossessed",
        "saves", "goalsConceded",
    ]

    X = np.array([[r.get(f, 0) or 0 for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r["rating"] for r in rows], dtype=float)

    if len(X) < 20:
        print(f"  {grupo_label}: muy pocas muestras ({len(X)}), saltando.")
        return None, FEATURES

    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X)

    # Ridge para evitar overfitting con features correlacionados
    model = Ridge(alpha=1.0)
    model.fit(X_sc, y)
    y_pred = model.predict(X_sc)
    r2 = r2_score(y, y_pred)

    print(f"\n{'='*55}")
    print(f"  Grupo: {grupo_label}  |  n={len(rows)}  |  R²={r2:.3f}")
    print(f"  Intercepto: {model.intercept_:.4f}")
    print(f"  {'Feature':<28}  {'Coef (std)':>12}  {'Coef (raw)':>12}")
    print(f"  {'-'*56}")

    # Coeficientes en unidades originales (desescalar)
    raw_coefs = model.coef_ / scaler.scale_
    intercept_raw = model.intercept_ - np.sum(raw_coefs * scaler.mean_)

    pairs = sorted(zip(FEATURES, model.coef_, raw_coefs), key=lambda x: abs(x[1]), reverse=True)
    for feat, c_std, c_raw in pairs:
        if abs(c_std) < 0.005:
            continue
        print(f"  {feat:<28}  {c_std:>+12.4f}  {c_raw:>+12.4f}")

    return {"model": model, "scaler": scaler, "features": FEATURES,
            "r2": r2, "raw_coefs": dict(zip(FEATURES, raw_coefs)),
            "intercept_raw": intercept_raw}, FEATURES


def predict_rating(model_info, stats_dict):
    import numpy as np
    features = model_info["features"]
    x = np.array([[stats_dict.get(f, 0) or 0 for f in features]], dtype=float)
    x_sc = model_info["scaler"].transform(x)
    return float(model_info["model"].predict(x_sc)[0])


def main():
    # Cargar event_ids de los partidos finalizados del Apertura 2026
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        data = json.load(f)

    finished_events = [
        p for p in data["partidos"]
        if p["estado"] == "finished"
    ]
    event_ids = [p["id"] for p in finished_events]
    print(f"Partidos finalizados: {len(event_ids)}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-UY",
            viewport={"width": 1280, "height": 800},
        ).new_page()

        print("Cargando SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        print(f"Descargando lineups de {len(event_ids)} partidos...")
        all_rows = collect_dataset(page, event_ids)
        browser.close()

    print(f"\nTotal filas con rating: {len(all_rows)}")

    # Guardar dataset crudo
    with open("apertura2026_dataset_ratings.json", "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print("Dataset guardado en apertura2026_dataset_ratings.json")

    # Regresión por grupo de posición
    models = {}
    for grupo in ["TODOS", "GK", "DEF", "MID", "FWD"]:
        subset = all_rows if grupo == "TODOS" else [r for r in all_rows if r["grupo"] == grupo]
        result, _ = run_regression(subset, grupo_label=grupo)
        if result:
            models[grupo] = result

    # Guardar coeficientes
    coefs_out = {}
    for grupo, m in models.items():
        coefs_out[grupo] = {
            "r2": m["r2"],
            "intercept": m["intercept_raw"],
            "coeficientes": {k: round(v, 6) for k, v in m["raw_coefs"].items()},
        }
    with open("apertura2026_formula_rating.json", "w", encoding="utf-8") as f:
        json.dump(coefs_out, f, ensure_ascii=False, indent=2)
    print("\nFórmula guardada en apertura2026_formula_rating.json")

    # Aplicar corrección a jugadores afectados
    # Cargamos los jugadores con discrepancias de goles
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        goles_data = json.load(f)

    # Jugadores con discrepancia incidents > lineups (gol no propagado a stats)
    afectados_eventos = []
    for partido in goles_data["partidos"]:
        for disc in partido.get("discrepancias", []):
            if disc["diferencia"] > 0:  # incidents > lineups → faltó gol en stats
                afectados_eventos.append({
                    "event_id":  partido["id"],
                    "fecha":     partido["fecha"],
                    "jornada":   partido["jornada"],
                    "partido":   f"{partido['local']} vs {partido['visitante']}",
                    "player_id": disc["player_id"],
                    "nombre":    disc["nombre"],
                    "goles_faltantes": disc["diferencia"],
                })

    # También Copelotti (corrección manual)
    afectados_eventos.append({
        "event_id":  15907398,
        "fecha":     "2026-03-31",
        "jornada":   9,
        "partido":   "Progreso vs Liverpool UY",
        "player_id": 1643434,
        "nombre":    "Matteo Copelotti",
        "goles_faltantes": 1,
        "fuente": "manual (ESPN Uruguay)",
    })

    print("\n=== CORRECCIONES DE RATING ===")
    print(f"  {'Jugador':<30}  {'J':>3}  {'Rating orig':>11}  {'Rating corr':>11}  {'Delta':>6}")
    print(f"  {'-'*70}")

    correcciones_rating = []
    row_by_event_player = {(r["event_id"], r["player_id"]): r for r in all_rows}

    for caso in afectados_eventos:
        ev_id = caso["event_id"]
        pid   = caso["player_id"]
        key   = (ev_id, pid)

        if key not in row_by_event_player:
            print(f"  {caso['nombre']:<30}  J{caso['jornada']:>2}  SIN DATOS en dataset")
            continue

        row = row_by_event_player[key]
        rating_orig = row["rating"]
        grupo = row.get("grupo", "TODOS")

        # Modelo del grupo (o TODOS si no hay)
        model_info = models.get(grupo) or models.get("TODOS")
        if not model_info:
            continue

        # Rating con stats corregidas (sumamos los goles faltantes)
        stats_corr = dict(row)
        stats_corr["goals"] = (stats_corr.get("goals") or 0) + caso["goles_faltantes"]
        rating_corr = predict_rating(model_info, stats_corr)

        # Clampeamos entre 1.0 y 10.0 (escala SofaScore)
        rating_corr = round(max(1.0, min(10.0, rating_corr)), 2)
        delta = round(rating_corr - rating_orig, 2)

        print(f"  {caso['nombre']:<30}  J{caso['jornada']:>2}  {rating_orig:>11.2f}  {rating_corr:>11.2f}  {delta:>+6.2f}")

        correcciones_rating.append({
            **caso,
            "grupo":        grupo,
            "rating_orig":  rating_orig,
            "rating_corr":  rating_corr,
            "delta_rating": delta,
            "stats_orig":   {f: row.get(f, 0) for f in ["goals", "assists", "minutesPlayed"]},
            "stats_corr":   {f: stats_corr.get(f, 0) for f in ["goals", "assists", "minutesPlayed"]},
        })

    with open("apertura2026_ratings_corregidos.json", "w", encoding="utf-8") as f:
        json.dump({
            "nota": "Rating corregido estimado via regresión Ridge sobre stats del Apertura 2026.",
            "modelos_r2": {k: round(v["r2"], 3) for k, v in models.items()},
            "correcciones": correcciones_rating,
        }, f, ensure_ascii=False, indent=2)

    print("\nGuardado en apertura2026_ratings_corregidos.json")


if __name__ == "__main__":
    main()
