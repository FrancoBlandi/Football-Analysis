"""
lpf_stats.py — Scraper estadísticas LPF (SofaScore) con enriquecimiento de perfil.

Uso:
    python lpf_stats.py --season-id 87913 --min-minutes 200 --output lpf_2026.csv

IDs SofaScore:
    LPF unique-tournament: 155
    Primera LPF 2026:      87913
    Torneo Clausura 2025:  77826
    Torneo Apertura 2025:  70268
"""

import sys
import io
import argparse
import csv
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STAT_FIELDS = [
    "goals", "assists", "yellowCards", "redCards", "rating",
    "minutesPlayed", "appearances",
    "tackles", "interceptions", "clearances",
    "keyPasses", "successfulDribbles", "totalContest",
    "accuratePasses", "totalPasses",
    "accurateLongBalls", "totalLongBalls",
    "accurateCrosses", "totalCross",
    "shotsOnTarget", "shotsOffTarget",
    "bigChancesCreated", "bigChancesMissed",
    "aerialDuelsWon", "aerialLost",
    "groundDuelsWon", "duelLost",
    "goalConversionPercentage", "penaltyGoals",
    "wasFouled", "fouls", "dispossessed", "possessionLost", "touches", "ballRecovery",
]

FIELDS_PARAM = ",".join(STAT_FIELDS)

RENAME_ES = {
    "player_id":              "player_id",
    "nombre":                 "Jugador",
    "posicion":               "Posicion",
    "edad":                   "Edad",
    "pais":                   "Pais",
    "club":                   "Club",
    "club_id":                "club_id",
    "goals":                  "Goles",
    "assists":                "Asistencias",
    "yellowCards":            "Amarillas",
    "redCards":               "Rojas",
    "rating":                 "Rating",
    "minutesPlayed":          "Minutos Jugados",
    "appearances":            "Partidos Jugados",
    "tackles":                "Entradas",
    "interceptions":          "Intercepciones",
    "clearances":             "Despejes",
    "keyPasses":              "Pases Clave",
    "successfulDribbles":     "Regates Exitosos",
    "totalContest":           "Regates Intentados",
    "accuratePasses":         "Pases Acertados",
    "totalPasses":            "Pases Totales",
    "accurateLongBalls":      "Pelotazos Acertados",
    "totalLongBalls":         "Pelotazos Totales",
    "accurateCrosses":        "Centros Acertados",
    "totalCross":             "Centros Totales",
    "shotsOnTarget":          "Remates al Arco",
    "shotsOffTarget":         "Remates Afuera",
    "bigChancesCreated":      "Grandes Chances Creadas",
    "bigChancesMissed":       "Grandes Chances Falladas",
    "aerialDuelsWon":         "Duelos Aereos Ganados",
    "aerialLost":             "Duelos Aereos Perdidos",
    "groundDuelsWon":         "Duelos en Suelo Ganados",
    "duelLost":               "Duelos en Suelo Perdidos",
    "goalConversionPercentage": "Conversion Goles %",
    "penaltyGoals":           "Goles de Penal",
    "wasFouled":              "Faltas Recibidas",
    "fouls":                  "Faltas Cometidas",
    "dispossessed":           "Robos Sufridos",
    "possessionLost":         "Posesion Perdida",
    "touches":                "Toques",
    "ballRecovery":           "Recuperaciones",
}


def calc_age(dob_timestamp: int):
    if not dob_timestamp:
        return None
    dob = date.fromtimestamp(dob_timestamp)
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def fetch_json(page, url: str) -> dict:
    result = page.evaluate(f"""
        async () => {{
            const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
            if (!resp.ok) return {{}};
            return await resp.json();
        }}
    """)
    return result or {}


def get_profile_map(page, tournament_id: int, season_id: int) -> dict:
    """Obtiene posición, edad y país de todos los jugadores via planteles."""
    teams_url = f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}/season/{season_id}/teams"
    teams_data = fetch_json(page, teams_url)
    teams = teams_data.get("teams", [])
    print(f"  Equipos en la temporada: {len(teams)}")

    profile_map = {}
    for team in teams:
        team_id = team["id"]
        squad_url = f"https://api.sofascore.com/api/v1/team/{team_id}/players"
        squad_data = fetch_json(page, squad_url)
        players = squad_data.get("players", [])
        for entry in players:
            p = entry.get("player", entry)
            pid = p.get("id")
            if not pid:
                continue
            profile_map[pid] = {
                "posicion": p.get("position", ""),
                "edad":     calc_age(p.get("dateOfBirthTimestamp")),
                "pais":     p.get("country", {}).get("name", ""),
            }
        page.wait_for_timeout(150)

    print(f"  Perfiles cargados: {len(profile_map)} jugadores")
    return profile_map


def fetch_league_page(page, tournament_id: int, season_id: int, limit: int, offset: int) -> dict:
    url = (
        f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}"
        f"/season/{season_id}/statistics"
        f"?limit={limit}&offset={offset}"
        f"&order=-rating&accumulation=total"
        f"&fields={FIELDS_PARAM}"
    )
    return fetch_json(page, url)


def scrape_season(tournament_id: int, season_id: int, min_minutes: int) -> list:
    from playwright.sync_api import sync_playwright

    all_players = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        ).new_page()

        print("Cargando SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        print("Obteniendo perfiles de plantel...")
        profile_map = get_profile_map(page, tournament_id, season_id)

        LIMIT = 100
        print(f"Fetching estadísticas (limit={LIMIT})...")
        first = fetch_league_page(page, tournament_id, season_id, LIMIT, 0)
        total_pages = first.get("pages", 1)
        print(f"Páginas: {total_pages}")

        def process(results: list):
            for entry in results:
                player_data = entry.get("player", {})
                team_data   = entry.get("team", {})
                pid         = player_data.get("id")
                minutes     = entry.get("minutesPlayed", 0) or 0
                if minutes < min_minutes:
                    continue
                profile = profile_map.get(pid, {})
                row = {
                    "player_id": pid,
                    "nombre":    player_data.get("name", ""),
                    "posicion":  profile.get("posicion", ""),
                    "edad":      profile.get("edad"),
                    "pais":      profile.get("pais", ""),
                    "club":      team_data.get("name", ""),
                    "club_id":   team_data.get("id"),
                }
                for campo in STAT_FIELDS:
                    row[campo] = entry.get(campo)
                all_players.append(row)

        process(first.get("results", []))
        print(f"  offset=0: {len(first.get('results', []))} jugadores")

        for offset in range(LIMIT, total_pages * LIMIT, LIMIT):
            data = fetch_league_page(page, tournament_id, season_id, LIMIT, offset)
            results = data.get("results", [])
            print(f"  offset={offset}: {len(results)} jugadores")
            process(results)
            if len(results) < LIMIT:
                break
            page.wait_for_timeout(200)

        browser.close()

    # Dedup y sort
    seen, deduped = set(), []
    for row in all_players:
        if row["player_id"] not in seen:
            seen.add(row["player_id"])
            deduped.append(row)
    deduped.sort(key=lambda x: x.get("rating") or 0, reverse=True)

    # Renombrar a español
    renamed = []
    for row in deduped:
        renamed.append({RENAME_ES.get(k, k): v for k, v in row.items()})

    print(f"Total con >= {min_minutes} min: {len(renamed)}")
    return renamed


def save_csv(players: list, output_path: str):
    if not players:
        print("Sin datos.")
        return
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(players[0].keys()))
        writer.writeheader()
        writer.writerows(players)
    print(f"CSV guardado: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tournament-id", type=int, default=155)
    parser.add_argument("--season-id",     type=int, default=87913)
    parser.add_argument("--min-minutes",   type=int, default=200)
    parser.add_argument("--output",        type=str, default="lpf_stats.csv")
    args = parser.parse_args()

    players = scrape_season(args.tournament_id, args.season_id, args.min_minutes)
    save_csv(players, args.output)

    print("\n--- TOP 10 por rating ---")
    for i, p in enumerate(players[:10], 1):
        print(f"  {i:2}. {p.get('Jugador',''):<25} {p.get('Club',''):<22} "
              f"min={str(p.get('Minutos Jugados','-')):>4}  rating={p.get('Rating','-')}")


if __name__ == "__main__":
    main()
