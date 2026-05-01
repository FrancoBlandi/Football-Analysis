"""
sofascore.py — Scraper de ratings y estadísticas de SofaScore usando Playwright.

Uso:
    python sofascore.py --player-id 928237 --output sosa_sofascore.json
    python sofascore.py --player-id 1153083 --output carboni_sofascore.json

IDs de jugadores en SofaScore:
    Santiago Sosa (Racing):     928237
    Valentín Carboni (Racing): 1153083
    Roger Sosa (Racing):        (buscar en URL de su perfil)

El ID se obtiene de la URL de SofaScore:
    https://www.sofascore.com/football/player/{nombre}/{ID}
"""

import sys
import io
import json
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def scrape_player(player_id: int) -> dict:
    from playwright.sync_api import sync_playwright

    result = {
        "player_id": player_id,
        "fuente": "SofaScore",
        "fecha_extraccion": __import__('datetime').date.today().isoformat(),
        "perfil": {},
        "estadisticas_temporada": []
    }

    api_responses = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 800}
        )

        def handle_response(response):
            if f"/api/v1/player/{player_id}" in response.url and response.status == 200:
                key = response.url.split(f"/player/{player_id}")[-1].strip("/") or "perfil"
                key = key.replace("/", "_") or "perfil"
                try:
                    api_responses[key] = response.json()
                except Exception:
                    pass

        page = context.new_page()
        page.on("response", handle_response)

        def fetch(ep):
            try:
                print(f"  Fetching: {ep}")
                page.goto(ep, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1200)  # Playwright-native: procesa eventos mientras espera
            except Exception as e:
                print(f"  Error en {ep}: {e}")

        print(f"Abriendo SofaScore para jugador {player_id}...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        # Paso 1 — perfil y temporadas
        fetch(f"https://api.sofascore.com/api/v1/player/{player_id}")
        fetch(f"https://api.sofascore.com/api/v1/player/{player_id}/statistics/seasons")

        # Paso 2 — leer types_map e iterar (los datos ya están en api_responses)
        types_map = api_responses.get("statistics_seasons", {}).get("typesMap", {})
        print(f"  Torneos disponibles: {list(types_map.keys())}")

        # Paso 3 — stats reales por torneo/temporada
        # Priorizar torneos conocidos (Liga Profesional Argentina = 155, Copa de la Liga = 13475)
        PRIORITY_IDS = ["155", "13475"]
        sorted_tournaments = (
            [(tid, s) for tid, s in types_map.items() if tid in PRIORITY_IDS] +
            [(tid, s) for tid, s in types_map.items() if tid not in PRIORITY_IDS]
        )

        # Fetchear temporadas conocidas que SofaScore omite del typesMap (ej: LPF 2026 en curso)
        EXTRA_ENDPOINTS = [
            f"https://api.sofascore.com/api/v1/player/{player_id}/unique-tournament/155/season/87913/statistics/overall",  # Primera LPF 2026
        ]
        for ep in EXTRA_ENDPOINTS:
            fetch(ep)
        fetched = 0
        for tournament_id, seasons in sorted_tournaments:
            for season_id in list(seasons.keys())[:2]:
                ep = (f"https://api.sofascore.com/api/v1/player/{player_id}"
                      f"/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall")
                fetch(ep)
                fetched += 1
                if fetched >= 16:
                    break
            if fetched >= 16:
                break

        browser.close()

    # ── Procesar respuestas interceptadas ──
    print(f"Endpoints interceptados: {list(api_responses.keys())}")

    # Perfil del jugador
    if "perfil" in api_responses:
        p_data = api_responses["perfil"].get("player", {})
        result["perfil"] = {
            "nombre":     p_data.get("name", ""),
            "posicion":   p_data.get("position", ""),
            "edad":       p_data.get("age"),
            "altura":     p_data.get("height"),
            "pie":        p_data.get("preferredFoot", ""),
            "pais":       p_data.get("country", {}).get("name", ""),
            "club":       p_data.get("team", {}).get("name", ""),
            "valor_eur":  p_data.get("proposedMarketValue"),
        }

    # Estadísticas de temporada — endpoint: unique-tournament/{t}/season/{s}/statistics/overall
    CAMPOS = ["rating", "appearances", "minutesPlayed", "goals", "assists",
              "yellowCards", "redCards", "tackles", "interceptions", "clearances",
              "aerialDuelsWon", "aerialDuelsLost", "groundDuelsWon", "groundDuelsLost",
              "successfulDribbles", "keyPasses", "accuratePasses", "totalPasses",
              "accurateLongBalls", "totalLongBalls", "bigChancesCreated",
              "shotsOnTarget", "shotsOffTarget", "expectedGoals", "expectedAssists"]

    for key, raw in api_responses.items():
        if "unique-tournament" not in key:
            continue
        stats_data = raw.get("statistics", {})
        if not stats_data:
            continue
        # Extraer tournament/season del nombre de la key
        # key = "unique-tournament_1024_season_88177_statistics_overall"
        parts = key.replace("-", "_").split("_")
        try:
            t_idx = parts.index("tournament") + 1
            s_idx = parts.index("season") + 1
            t_id = parts[t_idx]
            s_id = parts[s_idx]
        except (ValueError, IndexError):
            t_id = s_id = "?"

        # Nombre del torneo/temporada desde metadata si está disponible
        seasons_meta = api_responses.get("statistics_seasons", {})
        t_name = "?"
        s_name = "?"
        for ut in seasons_meta.get("uniqueTournamentSeasons", []):
            if str(ut.get("uniqueTournament", {}).get("id")) == str(t_id):
                t_name = ut.get("uniqueTournament", {}).get("name", t_id)
                for s in ut.get("seasons", []):
                    if str(s.get("id")) == str(s_id):
                        s_name = s.get("name", s_id)
                        break
                break

        entry = {"competicion": t_name, "temporada": s_name,
                 "tournament_id": t_id, "season_id": s_id}
        for campo in CAMPOS:
            if campo in stats_data:
                entry[campo] = stats_data[campo]
        result["estadisticas_temporada"].append(entry)

    result["_raw_keys"] = list(api_responses.keys())
    result["_raw"] = api_responses  # dump completo para inspección

    return result


def main():
    parser = argparse.ArgumentParser(description="Scraper SofaScore via Playwright")
    parser.add_argument("--player-id", type=int, required=True,
                        help="ID del jugador en SofaScore (de la URL del perfil)")
    parser.add_argument("--output", type=str, default=None,
                        help="Archivo de salida JSON (omitir para imprimir a stdout)")
    args = parser.parse_args()

    data = scrape_player(args.player_id)

    output_json = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Guardado en {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
