"""
apertura_goles.py — Verifica consistencia de goles en el Torneo Apertura 2026 (Liga AUF Uruguaya).

Compara dos fuentes internas de SofaScore:
  - /event/{id}/incidents  → eventos de gol registrados partido a partido
  - /event/{id}/lineups    → estadísticas de jugador (campo "goals")

Si hay diferencias → el partido está flaggeado como discrepancia.
Además agrega totales por jugador para detectar errores acumulados vs fuentes externas.

Uso:
    python apertura_goles.py
    python apertura_goles.py --season-id 80123 --output apertura2026_goles.json

IDs SofaScore:
    Liga AUF Uruguaya: tournament_id=278
    Temporada 2025:    season_id=71306  (Apertura Feb-May 2025)
    Temporada 2026:    se detecta automáticamente (busca la más reciente)
"""

import sys
import io
import json
import argparse
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TOURNAMENT_ID = 278

# Apertura 2026: aprox Feb 1 – May 25, 2026
# Usar Jun 1 00:00 UTC como corte para no mezclar con Intermedio
APERTURA_2026_START_TS = int(datetime(2026, 1, 25, 0, 0, 0, tzinfo=timezone.utc).timestamp())
APERTURA_2026_END_TS   = int(datetime(2026, 6,  1, 0, 0, 0, tzinfo=timezone.utc).timestamp())


def fetch_json(page, url: str) -> dict:
    result = page.evaluate(f"""
        async () => {{
            try {{
                const resp = await fetch('{url}', {{
                    headers: {{Accept: 'application/json'}}
                }});
                if (!resp.ok) return {{"_status": resp.status}};
                return await resp.json();
            }} catch(e) {{
                return {{"_error": e.toString()}};
            }}
        }}
    """)
    return result or {}


def find_latest_season(page, tournament_id: int) -> tuple:
    """Devuelve (season_id, season_name) de la temporada más reciente."""
    url = f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}/seasons"
    data = fetch_json(page, url)
    seasons = data.get("seasons", [])
    if not seasons:
        raise RuntimeError(f"No se encontraron temporadas para tournament={tournament_id}")
    # Las temporadas vienen ordenadas de más reciente a más antigua
    best = seasons[0]
    print(f"  Temporadas disponibles: {[s.get('name') for s in seasons[:5]]}")
    return best.get("id"), best.get("name", "")


def get_all_season_events(page, tournament_id: int, season_id: int) -> list:
    """Pagina todos los eventos de la temporada via /events/last/{page}."""
    all_events = []
    p = 0
    while True:
        url = f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}/season/{season_id}/events/last/{p}"
        data = fetch_json(page, url)
        events = data.get("events", [])
        all_events.extend(events)
        has_next = data.get("hasNextPage", False)
        print(f"  Página {p}: {len(events)} eventos, hasNextPage={has_next}")
        if not has_next or not events:
            break
        p += 1
        page.wait_for_timeout(200)
    return all_events


def get_incidents_goals(page, event_id: int) -> list:
    """
    Devuelve lista de goles desde /event/{id}/incidents.
    Cada gol: {"player_id", "nombre", "minuto", "tipo"}
    """
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/incidents"
    data = fetch_json(page, url)

    goals = []
    for inc in data.get("incidents", []):
        inc_type = inc.get("incidentType", "")
        # Filtra solo goles (no tarjetas, sustituciones, etc.)
        if inc_type not in ("goal", "penaltyScored"):
            continue
        player = inc.get("player", {})
        goals.append({
            "player_id": player.get("id"),
            "nombre":    player.get("name", ""),
            "minuto":    inc.get("time"),
            "tipo":      inc_type,
            "equipo":    "home" if not inc.get("isHome") is False else "away",
        })
    return goals


def get_lineups_goals(page, event_id: int) -> dict:
    """
    Devuelve dict player_id → goles desde /event/{id}/lineups (statistics.goals).
    """
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    data = fetch_json(page, url)

    result = {}
    for side in ["home", "away"]:
        side_data = data.get(side, {})
        for entry in side_data.get("players", []):
            p = entry.get("player", {})
            pid = p.get("id")
            if not pid:
                continue
            stats = entry.get("statistics") or {}
            goles = stats.get("goals", 0) or 0
            nombre = p.get("name", "")
            result[pid] = {"nombre": nombre, "goles_lineups": goles}
    return result


def cross_check_match(goals_inc: list, goals_lin: dict) -> list:
    """
    Cruza incidents vs lineups. Devuelve lista de discrepancias:
    jugadores donde la cantidad de goles difiere entre las dos fuentes.
    """
    # Contar goles por jugador desde incidents
    from collections import Counter
    counter_inc = Counter()
    nombre_inc = {}
    for g in goals_inc:
        pid = g.get("player_id")
        if pid:
            counter_inc[pid] += 1
            nombre_inc[pid] = g.get("nombre", "")

    discrepancias = []
    # Jugadores con goles según incidents
    for pid, count in counter_inc.items():
        lin_info = goals_lin.get(pid, {})
        lin_goals = lin_info.get("goles_lineups", 0)
        nombre = nombre_inc.get(pid) or lin_info.get("nombre", str(pid))
        if count != lin_goals:
            discrepancias.append({
                "player_id":       pid,
                "nombre":          nombre,
                "goles_incidents": count,
                "goles_lineups":   lin_goals,
                "diferencia":      count - lin_goals,
            })

    # Jugadores con goles en lineups pero no en incidents
    for pid, lin_info in goals_lin.items():
        if pid in counter_inc:
            continue
        lin_goals = lin_info.get("goles_lineups", 0)
        if lin_goals and lin_goals > 0:
            discrepancias.append({
                "player_id":       pid,
                "nombre":          lin_info.get("nombre", str(pid)),
                "goles_incidents": 0,
                "goles_lineups":   lin_goals,
                "diferencia":      -lin_goals,
            })

    return discrepancias


def scrape(season_id=None) -> dict:
    from playwright.sync_api import sync_playwright
    from collections import defaultdict

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

        if season_id is None:
            print("Buscando temporada más reciente...")
            season_id, season_name = find_latest_season(page, TOURNAMENT_ID)
            print(f"  → season_id={season_id}, nombre='{season_name}'")
        else:
            season_name = f"season_{season_id}"

        print(f"Obteniendo eventos de la temporada {season_id}...")
        all_events = get_all_season_events(page, TOURNAMENT_ID, season_id)
        print(f"Total eventos en temporada: {len(all_events)}")

        # Filtrar solo el Apertura por fecha
        apertura_events = [
            ev for ev in all_events
            if APERTURA_2026_START_TS <= ev.get("startTimestamp", 0) < APERTURA_2026_END_TS
        ]
        apertura_events.sort(key=lambda x: (x.get("startTimestamp", 0), x.get("roundInfo", {}).get("round", 0)))
        print(f"Partidos del Apertura 2026 (Jan 25 – Jun 1): {len(apertura_events)}")

        partidos = []
        total_goles_incidents = defaultdict(lambda: {"nombre": "", "goles": 0, "partidos": []})
        total_goles_lineups   = defaultdict(lambda: {"nombre": "", "goles": 0})

        for ev in apertura_events:
            ev_id       = ev.get("id")
            status_type = ev.get("status", {}).get("type", "")
            ts          = ev.get("startTimestamp", 0)
            fecha_str   = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
            home        = ev.get("homeTeam", {}).get("name", "?")
            away        = ev.get("awayTeam", {}).get("name", "?")
            jornada     = ev.get("roundInfo", {}).get("round", "?")
            home_score  = ev.get("homeScore", {}).get("current")
            away_score  = ev.get("awayScore", {}).get("current")
            resultado   = f"{home_score}-{away_score}" if home_score is not None else None

            print(f"  J{str(jornada):>2} | {fecha_str} | {home[:16]:<16} vs {away[:16]:<16} | {status_type}", end=" ...")

            if status_type != "finished":
                print(f" SKIP ({status_type})")
                partidos.append({
                    "id": ev_id, "jornada": jornada, "fecha": fecha_str,
                    "local": home, "visitante": away, "resultado": resultado,
                    "estado": status_type, "goles_incidents": [], "discrepancias": [],
                })
                continue

            goals_inc = get_incidents_goals(page, ev_id)
            goals_lin = get_lineups_goals(page, ev_id)
            discrepancias = cross_check_match(goals_inc, goals_lin)

            # Acumular totales por jugador desde incidents
            for g in goals_inc:
                pid = g.get("player_id")
                if pid:
                    total_goles_incidents[pid]["nombre"] = g.get("nombre", "")
                    total_goles_incidents[pid]["goles"] += 1
                    total_goles_incidents[pid]["partidos"].append({
                        "ev_id": ev_id, "fecha": fecha_str, "jornada": jornada,
                        "minuto": g.get("minuto"), "tipo": g.get("tipo"),
                        "partido": f"{home} vs {away}",
                    })

            # Acumular desde lineups
            for pid, info in goals_lin.items():
                total_goles_lineups[pid]["nombre"] = info["nombre"]
                total_goles_lineups[pid]["goles"] += info["goles_lineups"]

            flag = f" *** {len(discrepancias)} DISCREPANCIAS" if discrepancias else " OK"
            print(f" {len(goals_inc)} goles{flag}")

            if discrepancias:
                for d in discrepancias:
                    print(f"      ⚠ {d['nombre']}: incidents={d['goles_incidents']} lineups={d['goles_lineups']}")

            partidos.append({
                "id": ev_id, "jornada": jornada, "fecha": fecha_str,
                "local": home, "visitante": away, "resultado": resultado,
                "estado": status_type,
                "goles_incidents": goals_inc,
                "discrepancias": discrepancias,
            })
            page.wait_for_timeout(180)

        browser.close()

    # Construir tabla de goleadores desde incidents con flag de discrepancia vs lineups
    goleadores = []
    all_pids = set(total_goles_incidents.keys()) | set(total_goles_lineups.keys())
    for pid in all_pids:
        inc  = total_goles_incidents.get(pid, {})
        lin  = total_goles_lineups.get(pid, {})
        g_inc = inc.get("goles", 0)
        g_lin = lin.get("goles", 0)
        nombre = inc.get("nombre") or lin.get("nombre", str(pid))
        goleadores.append({
            "player_id":        pid,
            "nombre":           nombre,
            "goles_incidents":  g_inc,
            "goles_lineups":    g_lin,
            "discrepancia":     g_inc != g_lin,
            "diferencia":       g_inc - g_lin,
            "partidos":         inc.get("partidos", []),
        })

    goleadores.sort(key=lambda x: x["goles_incidents"], reverse=True)

    partidos_con_discrepancia = [p for p in partidos if p.get("discrepancias")]
    jugadores_con_discrepancia = [g for g in goleadores if g["discrepancia"]]

    print(f"\n=== RESUMEN ===")
    print(f"Partidos analizados:          {len(partidos)}")
    print(f"Con discrepancias:            {len(partidos_con_discrepancia)}")
    print(f"Jugadores con discrepancias:  {len(jugadores_con_discrepancia)}")

    if jugadores_con_discrepancia:
        print("\n--- Jugadores con discrepancias ---")
        for j in jugadores_con_discrepancia:
            print(f"  {j['nombre']:<30} incidents={j['goles_incidents']} lineups={j['goles_lineups']} diff={j['diferencia']:+d}")

    return {
        "torneo":           "Liga AUF Uruguaya — Torneo Apertura 2026",
        "tournament_id":    TOURNAMENT_ID,
        "season_id":        season_id,
        "fecha_extraccion": datetime.utcnow().strftime("%Y-%m-%d"),
        "total_partidos":   len(partidos),
        "partidos_con_discrepancias": len(partidos_con_discrepancia),
        "jugadores_con_discrepancias": len(jugadores_con_discrepancia),
        "goleadores": goleadores,
        "partidos": partidos,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season-id", type=int, default=None,
                        help="ID de temporada SofaScore (auto-detecta si se omite)")
    parser.add_argument("--output", type=str, default="apertura2026_goles.json")
    args = parser.parse_args()

    result = scrape(args.season_id)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {args.output}")


if __name__ == "__main__":
    main()
