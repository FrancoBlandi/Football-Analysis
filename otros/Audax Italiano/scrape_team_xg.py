"""
scrape_team_xg.py — Extrae xG por equipo de SofaScore para Liga de Primera Chile 2026.
Torneo: 11653 · Temporada: 88493

Uso:
    python scrape_team_xg.py --output liga_xg.json
"""
import sys, io, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TOURNAMENT_ID = 11653
SEASON_ID     = 88493

FIELDS = [
    "expectedGoals", "expectedGoalsAgainst",
    "goalsScored", "goalsConceded",
    "wins", "draws", "losses", "matches",
    "rating",
]

def scrape(output_path=None):
    from playwright.sync_api import sync_playwright

    api_responses = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )

        def handle(resp):
            url = resp.url
            if f"/unique-tournament/{TOURNAMENT_ID}" in url and resp.status == 200:
                key = url.split(f"/unique-tournament/{TOURNAMENT_ID}")[-1].strip("/").replace("/", "_") or "root"
                try:
                    api_responses[key] = resp.json()
                    print(f"  interceptado: {url}")
                except Exception:
                    pass

        page = ctx.new_page()
        page.on("response", handle)

        print("Abriendo SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        # ── Endpoint 1: estadísticas de equipos (tab statistics) ──
        for order in ["-expectedGoals", "-rating", "-goalsScored"]:
            fields_str = "%2C".join(FIELDS)
            ep = (
                f"https://api.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}"
                f"/season/{SEASON_ID}/statistics"
                f"?limit=20&offset=0&accumulation=total"
                f"&fields={fields_str}&group=total&order={order}"
            )
            try:
                page.goto(ep, wait_until="domcontentloaded", timeout=18000)
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"  error {ep}: {e}")

        # ── Endpoint 2: standings (a veces incluye xG) ──
        for typ in ["total", "home", "away"]:
            ep = (
                f"https://api.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}"
                f"/season/{SEASON_ID}/standings/{typ}"
            )
            try:
                page.goto(ep, wait_until="domcontentloaded", timeout=18000)
                page.wait_for_timeout(800)
            except Exception as e:
                print(f"  error {ep}: {e}")

        # ── Endpoint 3: navegar a la página real de estadísticas del torneo ──
        try:
            page.goto(
                f"https://www.sofascore.com/football/tournament/chile/primera-division/{TOURNAMENT_ID}#id:{SEASON_ID},tab:statistics",
                wait_until="domcontentloaded", timeout=25000,
            )
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  error navegando torneo: {e}")

        browser.close()

    print(f"\nEndpoints interceptados ({len(api_responses)}):")
    for k in api_responses:
        print(f"  {k}")

    # ── Procesar respuestas ──
    result = {"teams": [], "_raw": api_responses}

    # Buscar en cualquier clave que tenga 'statistics' o 'standings'
    teams_found = {}

    for key, raw in api_responses.items():
        # Tabla de estadísticas por equipo
        rows = raw.get("statistics", raw.get("results", []))
        if isinstance(rows, list):
            for row in rows:
                team = row.get("team", {})
                tid  = team.get("id")
                if not tid:
                    continue
                entry = teams_found.setdefault(tid, {"team": team.get("name","?"), "id": tid})
                for f in FIELDS:
                    if f in row:
                        entry[f] = row[f]

        # Standings (puede traer xG en algunos torneos)
        rows2 = raw.get("standings", [])
        if isinstance(rows2, list):
            for group in rows2:
                for row in group.get("rows", []):
                    team = row.get("team", {})
                    tid  = team.get("id")
                    if not tid:
                        continue
                    entry = teams_found.setdefault(tid, {"team": team.get("name","?"), "id": tid})
                    for f in ["wins","draws","losses","scoresFor","scoresAgainst","points"]:
                        if f in row:
                            entry[f] = row[f]

    result["teams"] = sorted(teams_found.values(), key=lambda x: (x.get("expectedGoals") or 0), reverse=True)

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\nGuardado en {output_path}")
    else:
        print(out)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    scrape(args.output)
