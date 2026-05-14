"""
apertura2026_analisis_final.py — Análisis limpio de goles y asistencias del Apertura 2026.

Correcciones respecto a versiones anteriores:
  - Filtra incidentClass=="ownGoal" en incidents (autogoles no cuentan como gol del jugador)
  - Solo aplica corrección manual confirmada por prensa: Copelotti +1 / Paz -1 (J9)
  - Usa regresión Ridge por posición para estimar impacto en rating

Errores verificados por prensa (únicos reales):
  - J9 Progreso vs Liverpool 3-3 (2026-03-31):
      Nicolás Paz NO anotó — el gol del min ~41 fue de Matteo Copelotti (min 40)
      Fuente: ESPN Uruguay crónica del partido
"""

import sys, io, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TOURNAMENT_ID = 278
APERTURA_START = 1738800000   # 2026-01-26
APERTURA_END   = 1748736000   # 2026-06-01

# ─── IDs conocidos ────────────────────────────────────────────────────────────
COPELOTTI_ID = 1643434   # Matteo Copelotti (Progreso)
PAZ_ID       = 2059740   # Nicolás Agustín Paz (Progreso)
EV_J9        = 15907398  # Progreso vs Liverpool UY, J9, 2026-03-31


def fetch_json(page, url):
    r = page.evaluate(f"""
        async () => {{
            try {{
                const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
                if (!resp.ok) return {{"_status": resp.status}};
                return await resp.json();
            }} catch(e) {{ return {{"_error": e.toString()}}; }}
        }}
    """)
    return r or {}


# ─── Incidents ────────────────────────────────────────────────────────────────

def get_incidents(page, event_id):
    """
    Devuelve (goles, asistencias) por jugador desde incidents.
    Excluye incidentClass=="ownGoal".
    goles/asistencias = dict {player_id: {"nombre": str, "count": int, "eventos": list}}
    """
    data = fetch_json(page, f"https://api.sofascore.com/api/v1/event/{event_id}/incidents")
    goles  = defaultdict(lambda: {"nombre": "", "count": 0, "minutos": []})
    asists = defaultdict(lambda: {"nombre": "", "count": 0, "minutos": []})

    for inc in data.get("incidents", []):
        tipo  = inc.get("incidentType", "")
        clase = inc.get("incidentClass", "")
        if tipo not in ("goal", "penaltyScored"):
            continue
        if clase == "ownGoal":
            continue  # autogol: no cuenta como gol del jugador

        minuto = inc.get("time")

        scorer = inc.get("player", {})
        pid_s  = scorer.get("id")
        if pid_s:
            goles[pid_s]["nombre"] = scorer.get("name", "")
            goles[pid_s]["count"] += 1
            goles[pid_s]["minutos"].append(minuto)

        assist = inc.get("assist1") or {}
        pid_a  = assist.get("id")
        if pid_a:
            asists[pid_a]["nombre"] = assist.get("name", "")
            asists[pid_a]["count"] += 1
            asists[pid_a]["minutos"].append(minuto)

    return goles, asists


# ─── Lineups ──────────────────────────────────────────────────────────────────

def get_lineups(page, event_id):
    """
    Devuelve stats por jugador desde lineups.
    Retorna dict {player_id: {nombre, goles, asistencias, rating, posicion, ...stats}}
    """
    data = fetch_json(page, f"https://api.sofascore.com/api/v1/event/{event_id}/lineups")
    result = {}
    for side in ["home", "away"]:
        for entry in data.get(side, {}).get("players", []):
            p     = entry.get("player", {})
            pid   = p.get("id")
            if not pid:
                continue
            stats = entry.get("statistics") or {}
            result[pid] = {
                "nombre":      p.get("name", ""),
                "posicion":    p.get("position", ""),
                "rating":      stats.get("rating"),
                "goles":       stats.get("goals", 0) or 0,
                "asistencias": stats.get("goalAssist", 0) or stats.get("assists", 0) or 0,
                "minutos":     stats.get("minutesPlayed", 0) or 0,
                "stats_full":  stats,
            }
    return result


# ─── Cross-check ─────────────────────────────────────────────────────────────

def cross_check(inc_dict, lin_dict, campo):
    """Compara incidents vs lineups. Devuelve discrepancias en ambas direcciones."""
    all_pids = set(inc_dict) | {p for p, d in lin_dict.items() if d.get(campo, 0)}
    discs = []
    for pid in all_pids:
        n_inc = inc_dict.get(pid, {}).get("count", 0)
        n_lin = lin_dict.get(pid, {}).get(campo, 0) or 0
        if n_inc != n_lin:
            nombre = (inc_dict.get(pid) or {}).get("nombre") or lin_dict.get(pid, {}).get("nombre", str(pid))
            discs.append({
                "player_id": pid, "nombre": nombre,
                "incidents": n_inc, "lineups": n_lin,
                "diferencia": n_inc - n_lin,
                "direccion": "subestimado" if n_inc > n_lin else "sobreestimado",
            })
    return discs


# ─── Regresión ───────────────────────────────────────────────────────────────

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
        X = np.array([[r.get(f, 0) or 0 for f in FEATURES] for r in rows], dtype=float)
        y = np.array([r["rating"] for r in rows], dtype=float)
        sc = StandardScaler()
        X_sc = sc.fit_transform(X)
        m = Ridge(alpha=1.0).fit(X_sc, y)
        r2 = r2_score(y, m.predict(X_sc))
        raw_coefs = m.coef_ / sc.scale_
        intercept_raw = m.intercept_ - (raw_coefs * sc.mean_).sum()
        models[label] = {
            "model": m, "scaler": sc, "r2": r2,
            "raw_coefs": dict(zip(FEATURES, raw_coefs)),
            "intercept_raw": intercept_raw,
        }
        print(f"  Modelo {label}: n={len(rows)}, R²={r2:.3f}")
    return models


def predict(model_info, stats_dict):
    import numpy as np
    x = np.array([[stats_dict.get(f, 0) or 0 for f in FEATURES]], dtype=float)
    x_sc = model_info["scaler"].transform(x)
    return float(model_info["model"].predict(x_sc)[0])


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright

    # Cargar event_ids del Apertura 2026
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        base_data = json.load(f)

    finished = [p for p in base_data["partidos"] if p["estado"] == "finished"]
    print(f"Partidos finalizados: {len(finished)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-UY", viewport={"width": 1280, "height": 800},
        ).new_page()

        print("Cargando SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        # ── Paso 1: recolectar stats completas por jugador/partido para regresión ──
        print("\n[1/3] Descargando lineups para dataset de regresión...")
        dataset_rows = []
        for i, p in enumerate(finished, 1):
            lin = get_lineups(page, p["id"])
            for pid, info in lin.items():
                if info["rating"] is None:
                    continue
                stats = info.get("stats_full", {})
                row = {
                    "player_id": pid,
                    "nombre":    info["nombre"],
                    "event_id":  p["id"],
                    "grupo":     POS_MAP.get(info["posicion"], "UNK"),
                    "rating":    info["rating"],
                }
                for f in FEATURES:
                    row[f] = stats.get(f, 0) or 0
                row["goals"]   = info["goles"]
                row["assists"] = info["asistencias"]
                dataset_rows.append(row)
            if i % 20 == 0:
                print(f"  {i}/{len(finished)} partidos — {len(dataset_rows)} filas")
            page.wait_for_timeout(100)

        print(f"  Total filas con rating: {len(dataset_rows)}")

        # ── Paso 2: cross-check incidents vs lineups (con filtro autogoles) ──
        print("\n[2/3] Cross-check incidents vs lineups...")
        discrepancias_goles = []
        discrepancias_asist = []

        for p in finished:
            ev_id    = p["id"]
            jornada  = p["jornada"]
            partido  = f"{p['local']} vs {p['visitante']}"
            g_inc, a_inc = get_incidents(page, ev_id)
            lin = get_lineups(page, ev_id)

            dg = cross_check(g_inc, lin, "goles")
            da = cross_check(a_inc, lin, "asistencias")

            for d in dg:
                d.update({"event_id": ev_id, "jornada": jornada, "partido": partido})
                discrepancias_goles.append(d)
            for d in da:
                d.update({"event_id": ev_id, "jornada": jornada, "partido": partido})
                discrepancias_asist.append(d)

            page.wait_for_timeout(100)

        browser.close()

    # ── Paso 3: entrenar modelos ──
    print("\n[3/3] Entrenando modelos de rating...")
    models = train_models(dataset_rows)

    # ── Resumen cross-check ──
    sub_g  = [d for d in discrepancias_goles if d["diferencia"] > 0]
    sob_g  = [d for d in discrepancias_goles if d["diferencia"] < 0]
    sub_a  = [d for d in discrepancias_asist if d["diferencia"] > 0]
    sob_a  = [d for d in discrepancias_asist if d["diferencia"] < 0]

    print(f"\n{'='*60}")
    print(f"CROSS-CHECK (incidents filtrados sin autogoles) vs lineups")
    print(f"  Goles subestimados:     {len(sub_g)}")
    print(f"  Goles sobreestimados:   {len(sob_g)}")
    print(f"  Asist subestimadas:     {len(sub_a)}")
    print(f"  Asist sobreestimadas:   {len(sob_a)}")

    def print_discs(rows, titulo):
        if not rows:
            print(f"\n  {titulo}: ninguno")
            return
        print(f"\n  {titulo}:")
        for d in sorted(rows, key=lambda x: x["jornada"]):
            j = d["jornada"]
            j_str = f"J{j}*" if isinstance(j, int) and j >= 15 else f"J{j}"
            print(f"    {j_str:>4}  {d['nombre']:<30}  inc={d['incidents']}  lin={d['lineups']}  diff={d['diferencia']:+d}  | {d['partido']}")

    print_discs(sub_g, "Goles subestimados (incidents>lineups)")
    print_discs(sob_g, "Goles sobreestimados (lineups>incidents)")
    print_discs(sub_a, "Asist subestimadas (incidents>lineups)")
    print_discs(sob_a, "Asist sobreestimadas (lineups>incidents)")

    # ── Correcciones manuales confirmadas por prensa ──
    CORRECCIONES = [
        {
            "player_id": COPELOTTI_ID,
            "nombre":    "Matteo Copelotti",
            "event_id":  EV_J9,
            "jornada":   9,
            "partido":   "Progreso vs Liverpool UY",
            "campo":     "goals",
            "delta":     +1,
            "fuente":    "ESPN Uruguay — gol min 40 (SofaScore lo atribuyó a Nicolás Paz)",
        },
        {
            "player_id": PAZ_ID,
            "nombre":    "Nicolás Agustín Paz",
            "event_id":  EV_J9,
            "jornada":   9,
            "partido":   "Progreso vs Liverpool UY",
            "campo":     "goals",
            "delta":     -1,
            "fuente":    "ESPN Uruguay — gol del min ~41 era de Copelotti, no de Paz",
        },
    ]

    # ── Aplicar correcciones y recalcular ratings ──
    row_by_key = {(r["event_id"], r["player_id"]): r for r in dataset_rows}

    print(f"\n{'='*60}")
    print("CORRECCIONES DE RATING (solo errores verificados por prensa)")
    print(f"  {'Jugador':<30}  {'J':>3}  {'Rating orig':>11}  {'Rating corr':>11}  {'Delta':>6}")
    print(f"  {'-'*68}")

    correcciones_out = []
    for corr in CORRECCIONES:
        key = (corr["event_id"], corr["player_id"])
        row = row_by_key.get(key)
        if not row:
            print(f"  {corr['nombre']:<30}  J{corr['jornada']:>2}  SIN DATOS")
            continue

        rating_orig = row["rating"]
        grupo = row.get("grupo", "TODOS")
        model_info = models.get(grupo) or models.get("TODOS")

        stats_corr = dict(row)
        stats_corr["goals"] = max(0, (stats_corr.get("goals") or 0) + corr["delta"])

        rating_corr = round(max(1.0, min(10.0, predict(model_info, stats_corr))), 2)
        delta = round(rating_corr - rating_orig, 2)

        print(f"  {corr['nombre']:<30}  J{corr['jornada']:>2}  {rating_orig:>11.2f}  {rating_corr:>11.2f}  {delta:>+6.2f}")
        correcciones_out.append({**corr, "grupo": grupo, "rating_orig": rating_orig,
                                  "rating_corr": rating_corr, "delta_rating": delta})

    # ── Guardar resultados ──
    output = {
        "torneo":           "Liga AUF Uruguaya — Torneo Apertura 2026",
        "fecha_extraccion": __import__("datetime").date.today().isoformat(),
        "nota": (
            "Autogoles excluidos del conteo de incidents. "
            "Única corrección manual aplicada: gol de Copelotti min 40 atribuido erróneamente a Paz (J9). "
            "Verificado por ESPN Uruguay."
        ),
        "cross_check": {
            "goles_subestimados":   sub_g,
            "goles_sobreestimados": sob_g,
            "asist_subestimadas":   sub_a,
            "asist_sobreestimadas": sob_a,
        },
        "modelos_r2": {k: round(v["r2"], 3) for k, v in models.items()},
        "correcciones_verificadas": correcciones_out,
    }

    with open("apertura2026_analisis_final.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\nGuardado en apertura2026_analisis_final.json")


if __name__ == "__main__":
    main()
