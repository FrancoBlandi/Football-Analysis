"""
corregir_goles.py — Aplica correcciones al dataset de goles del Apertura 2026.

Fuente base: apertura2026_goles.json
  - goles_incidents es más confiable que goles_lineups en todos los casos.
  - Correcciones manuales adicionales para errores de captura (no detectables automáticamente).

Correcciones manuales aplicadas:
  - Matteo Copelotti (Progreso vs Liverpool UY, J9, 2026-03-31):
      SofaScore incidents = 1 (min 21), real = 2 (min 21 + min 40).
      Fuente: prensa ESPN Uruguay, minutos confirmados.
"""

import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Correcciones manuales: player_id -> {delta, nota, fuente}
CORRECCIONES_MANUALES = {
    1643434: {  # Matteo Copelotti
        "delta": 1,
        "nota":  "Gol min 40 no registrado en incidents. SofaScore solo registró min 21.",
        "fuente": "ESPN Uruguay — Progreso vs Liverpool UY (2026-03-31)",
        "partido_corregido": {"ev_id": 15907398, "fecha": "2026-03-31", "jornada": 9,
                              "minuto": 40, "tipo": "goal",
                              "partido": "Progreso vs Liverpool UY"},
    },
}

# Jugadores donde incidents != lineups pero incidents es correcto
# (documentados para trazabilidad)
CORRECCIONES_INCIDENTS = {
    # Estos ya quedan corregidos al usar goles_incidents como base
    "Gary Kagelmacher":      {"jornada": 1,  "partido": "Peñarol vs Montevideo City Torque",    "incidents": 1, "lineups": 0},
    "Alan Garcia":           {"jornada": 3,  "partido": "Montevideo Wanderers vs M. City",      "incidents": 1, "lineups": 0},
    "Ivo Costantino":        {"jornada": 4,  "partido": "Danubio vs Progreso",                  "incidents": 1, "lineups": 0},
    "Facundo Kidd":          {"jornada": 4,  "partido": "Danubio vs Progreso",                  "incidents": 1, "lineups": 0},
    "Fernando Mimbacas":     {"jornada": 10, "partido": "Racing de Montevideo vs Juventud",     "incidents": 2, "lineups": 1},
    "Álvaro López":          {"jornada": 10, "partido": "Albion FC vs Cerro Largo",             "incidents": 3, "lineups": 2},
    "Ignacio Rodríguez":     {"jornada": 13, "partido": "Central Español vs CA Cerro",          "incidents": 1, "lineups": 0},
}

TIMING_ARTIFACTS = ["Diego Vera", "Raúl Andrés Tarragona Lemos", "Ramiro Peralta",
                    "Nahuel Da Silva", "Facundo Silvera", "Nahuel López", "Alejo Cruz", "Lucas Agazzi"]


def corregir():
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        data = json.load(f)

    goleadores_corr = []

    for g in data["goleadores"]:
        pid   = g["player_id"]
        nombre = g["nombre"]

        # Base: incidents (ya más confiable que lineups)
        goles_base = g["goles_incidents"]
        partidos   = list(g.get("partidos", []))  # copia

        correcciones_aplicadas = []

        # ¿Es un artefacto de timing (J15, hoy)?
        es_timing = nombre in TIMING_ARTIFACTS
        if es_timing:
            # Para timing artifacts, el count de incidents puede tener +1 por partido no finalizado
            # Pero el partido SÍ terminó (finished), solo que stats no se procesaron.
            # Mantenemos incidents como base y lo notamos.
            correcciones_aplicadas.append({
                "tipo": "timing_artifact",
                "nota": "Partido del 2026-05-09 o 2026-05-10. Stats de lineups no procesadas aún. Incidents es base correcta.",
            })

        # Correcciones manuales por encima de incidents
        if pid in CORRECCIONES_MANUALES:
            cm = CORRECCIONES_MANUALES[pid]
            goles_base += cm["delta"]
            partidos.append(cm["partido_corregido"])
            # Ordenar por fecha/minuto
            partidos.sort(key=lambda x: (x.get("fecha", ""), x.get("minuto") or 0))
            correcciones_aplicadas.append({
                "tipo": "manual",
                "delta": cm["delta"],
                "nota": cm["nota"],
                "fuente": cm["fuente"],
            })

        # Correcciones por discrepancia incidents vs lineups (solo documentar)
        if nombre in CORRECCIONES_INCIDENTS:
            ci = CORRECCIONES_INCIDENTS[nombre]
            correcciones_aplicadas.append({
                "tipo": "incidents_sobre_lineups",
                "jornada": ci["jornada"],
                "partido": ci["partido"],
                "incidents": ci["incidents"],
                "lineups":   ci["lineups"],
                "nota": "incidents corrige lineups (gol registrado en evento pero no propagado a stats).",
            })

        goleadores_corr.append({
            "player_id":         pid,
            "nombre":            nombre,
            "goles_corregidos":  goles_base,
            "goles_sofascore_incidents": g["goles_incidents"],
            "goles_sofascore_lineups":   g["goles_lineups"],
            "correcciones":      correcciones_aplicadas,
            "partidos":          partidos,
        })

    # Reordenar por goles corregidos
    goleadores_corr.sort(key=lambda x: x["goles_corregidos"], reverse=True)

    result = {
        "torneo":           "Liga AUF Uruguaya — Torneo Apertura 2026",
        "fecha_extraccion": data["fecha_extraccion"],
        "nota": (
            "Goles corregidos = incidents (base) + correcciones manuales confirmadas por prensa. "
            "Los errores incidents>lineups quedan subsanados al usar incidents como base. "
            "Los artefactos J15 (partidos del 9-10 May) se mantienen en incidents hasta que SofaScore procese los stats."
        ),
        "total_jugadores_con_goles": sum(1 for g in goleadores_corr if g["goles_corregidos"] > 0),
        "correcciones_aplicadas": {
            "manuales": len(CORRECCIONES_MANUALES),
            "incidents_sobre_lineups": len(CORRECCIONES_INCIDENTS),
            "timing_artifacts": len(TIMING_ARTIFACTS),
        },
        "goleadores": goleadores_corr,
    }

    with open("apertura2026_goles_corregidos.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=== TABLA DE GOLEADORES CORREGIDA ===")
    print(f"{'Pos':>3}  {'Jugador':<32}  {'Goles':>5}  {'Nota'}")
    print("-" * 70)
    pos = 0
    prev = -1
    for g in goleadores_corr:
        if g["goles_corregidos"] == 0:
            break
        if g["goles_corregidos"] != prev:
            pos += 1
            prev = g["goles_corregidos"]
        flag = ""
        for c in g["correcciones"]:
            if c["tipo"] == "manual":
                flag = f"  [+{c['delta']} manual: {c['fuente'][:40]}]"
            elif c["tipo"] == "incidents_sobre_lineups" and not flag:
                flag = f"  [corr. incidents>lineups J{c['jornada']}]"
        print(f"  {pos:>2}. {g['nombre']:<32}  {g['goles_corregidos']:>2}     {flag}")

    print(f"\nGuardado en apertura2026_goles_corregidos.json")


if __name__ == "__main__":
    corregir()
