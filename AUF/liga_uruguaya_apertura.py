"""
liga_uruguaya_apertura.py — Trae todos los partidos del Apertura 2025 (Liga AUF Uruguaya)
y verifica si cada partido tiene ratings de jugadores en SofaScore.

Estructura de temporada 2025 (season_id=71306):
    Apertura:   Rondas 1-15,  Feb 1 – May 19, 2025
    Intermedio: Rondas 1-7,   May 23 – Jul 6, 2025
    Clausura:   Rondas 1-15,  Ago 1 – Nov 9, 2025
    Playoffs:   Semis + Final, Nov 2025

El script filtra por fecha para aislar solo el Apertura.

Uso:
    python liga_uruguaya_apertura.py
    python liga_uruguaya_apertura.py --output apertura.json

IDs SofaScore:
    Liga AUF Uruguaya: tournament_id=278, season_id=71306
"""

import sys
import io
import json
import argparse
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TOURNAMENT_ID = 278
SEASON_ID     = 71306  # Liga AUF Uruguaya 2025

# El Apertura 2025 corre de Feb 1 a May 19.
# Usamos May 21 00:00 UTC como corte para excluir el Intermedio (empieza May 23).
APERTURA_END_TS = int(datetime(2025, 5, 21, 0, 0, 0, tzinfo=timezone.utc).timestamp())


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
        page.wait_for_timeout(250)
    return all_events


def check_lineups(page, event_id: int) -> dict:
    """Verifica si el partido tiene lineups con ratings de jugadores."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    data = fetch_json(page, url)

    if not data or data.get("_status") or data.get("_error"):
        return {"tiene_ratings": False, "motivo": "sin_lineups"}

    home = data.get("home", {})
    away = data.get("away", {})

    con_rating = 0
    sin_rating = 0
    tiene_jugadores = False

    for side in [home, away]:
        for entry in side.get("players", []):
            tiene_jugadores = True
            stats = entry.get("statistics") or {}
            rating = stats.get("rating")
            if rating is not None:
                con_rating += 1
            else:
                sin_rating += 1

    if not tiene_jugadores:
        return {"tiene_ratings": False, "motivo": "lineups_vacias"}

    tiene = con_rating > 0
    return {
        "tiene_ratings": tiene,
        "jugadores_con_rating": con_rating,
        "jugadores_sin_rating": sin_rating,
        "motivo": None if tiene else "ratings_en_cero",
    }


def parse_event(event: dict, lineups_info: dict) -> dict:
    home       = event.get("homeTeam", {})
    away       = event.get("awayTeam", {})
    home_score = event.get("homeScore", {})
    away_score = event.get("awayScore", {})

    ts        = event.get("startTimestamp")
    fecha_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"

    resultado = None
    if home_score.get("current") is not None:
        resultado = f"{home_score['current']}-{away_score.get('current', '?')}"

    status = event.get("status", {}).get("type", "")
    rinfo  = event.get("roundInfo", {})

    row = {
        "id":         event.get("id"),
        "jornada":    rinfo.get("round"),
        "fecha":      fecha_str,
        "local":      home.get("name", ""),
        "visitante":  away.get("name", ""),
        "resultado":  resultado,
        "estado":     status,
        "tiene_ratings": lineups_info.get("tiene_ratings", False),
    }
    if lineups_info.get("tiene_ratings"):
        row["jugadores_con_rating"] = lineups_info.get("jugadores_con_rating")
        row["jugadores_sin_rating"] = lineups_info.get("jugadores_sin_rating")
    else:
        row["motivo_sin_ratings"] = lineups_info.get("motivo")

    return row


def scrape() -> dict:
    from playwright.sync_api import sync_playwright

    partidos = []

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

        print(f"Obteniendo todos los eventos de la temporada 2025 (season={SEASON_ID})...")
        all_events = get_all_season_events(page, TOURNAMENT_ID, SEASON_ID)
        print(f"Total eventos en la temporada: {len(all_events)}")

        # Filtrar solo los del Apertura (antes del May 21, 2025)
        apertura_events = [
            ev for ev in all_events
            if ev.get("startTimestamp", 0) < APERTURA_END_TS
        ]
        # Ordenar por fecha
        apertura_events.sort(key=lambda x: (x.get("startTimestamp", 0), x.get("roundInfo", {}).get("round", 0)))

        print(f"Partidos del Apertura (hasta May 21): {len(apertura_events)}")

        for ev in apertura_events:
            ev_id       = ev.get("id")
            status_type = ev.get("status", {}).get("type", "")
            ts          = ev.get("startTimestamp", 0)
            fecha_str   = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
            home        = ev.get("homeTeam", {}).get("name", "?")
            away        = ev.get("awayTeam", {}).get("name", "?")
            jornada     = ev.get("roundInfo", {}).get("round", "?")

            print(f"  J{str(jornada):>2} | {fecha_str} | {home[:16]:<16} vs {away[:16]:<16} | {status_type}", end=" ... ")

            if status_type == "finished":
                lineups_info = check_lineups(page, ev_id)
            else:
                lineups_info = {"tiene_ratings": False, "motivo": f"partido_{status_type}"}

            tiene = lineups_info.get("tiene_ratings", False)
            print("OK" if tiene else f"SIN RATINGS ({lineups_info.get('motivo','')})")

            row = parse_event(ev, lineups_info)
            partidos.append(row)
            page.wait_for_timeout(150)

        browser.close()

    con = sum(1 for p in partidos if p.get("tiene_ratings"))
    sin = len(partidos) - con

    return {
        "torneo":           "Liga AUF Uruguaya — Torneo Apertura 2025",
        "tournament_id":    TOURNAMENT_ID,
        "season_id":        SEASON_ID,
        "fecha_extraccion": datetime.utcnow().strftime("%Y-%m-%d"),
        "total_partidos":   len(partidos),
        "con_ratings":      con,
        "sin_ratings":      sin,
        "partidos":         partidos,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="liga_uruguaya_apertura.json")
    args = parser.parse_args()

    result = scrape()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {args.output}")

    print(f"\n=== RESUMEN ===")
    print(f"Torneo:         {result.get('torneo')}")
    print(f"Total partidos: {result.get('total_partidos')}")
    print(f"Con ratings:    {result.get('con_ratings')}")
    print(f"Sin ratings:    {result.get('sin_ratings')}")

    print("\n--- Partidos SIN ratings ---")
    for p in result.get("partidos", []):
        if not p.get("tiene_ratings"):
            local     = p.get("local", "")
            visitante = p.get("visitante", "")
            resultado = p.get("resultado") or p.get("estado", "?")
            motivo    = p.get("motivo_sin_ratings", "")
            print(f"  J{str(p.get('jornada','')):>2} | {p.get('fecha','?')} | "
                  f"{local:>22} vs {visitante:<22} | {resultado:>5} | {motivo}")


if __name__ == "__main__":
    main()
