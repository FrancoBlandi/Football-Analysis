"""
scrape_liga_players_xg.py
Extrae xG, bigChancesCreated, bigChancesMissed y goles de todos los jugadores
de la Liga de Primera Chile 2026 via SofaScore, luego los agrupa por equipo.

Torneo: 11653 (Liga de Primera Chile)  ·  Temporada: 88493 (2026)

Uso:
    python scrape_liga_players_xg.py --output liga_players_xg.json
"""
import sys, io, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TOURNAMENT_ID = 11653
SEASON_ID     = 88493

PLAYER_FIELDS = [
    "expectedGoals", "expectedAssists",
    "bigChancesCreated", "bigChancesMissed",
    "goals", "goalAssist",
    "rating", "minutesPlayed", "appearances",
    "shotsOnTarget", "shotsOffTarget",
]

GROUPS = ["attacking", "summary", "general", "total", ""]

def scrape(output_path=None):
    from playwright.sync_api import sync_playwright

    api_responses = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )

        def handle(resp):
            url = resp.url
            if (f"/unique-tournament/{TOURNAMENT_ID}" in url or
                f"/top-players" in url) and resp.status == 200:
                key = url.split("sofascore.com")[-1][:120]
                try:
                    api_responses[key] = resp.json()
                    print(f"  OK: {url[:110]}")
                except Exception:
                    pass

        page = ctx.new_page()
        page.on("response", handle)

        print("Paso 1: SofaScore home...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        fields_str = "%2C".join(PLAYER_FIELDS)

        # ── Endpoint 1: estadísticas de jugadores con paginación ──
        # ~400 jugadores activos en 16 equipos → pages en offset 0, 100, 200, 300, 400
        for offset in range(0, 500, 100):
            for order in ["-rating", "-goals", "-bigChancesCreated", "-minutesPlayed"]:
                ep = (
                    f"https://api.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}"
                    f"/season/{SEASON_ID}/statistics"
                    f"?limit=100&offset={offset}&accumulation=total"
                    f"&fields={fields_str}&order={order}"
                )
                try:
                    page.goto(ep, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(500)
                except Exception as e:
                    print(f"  error: {e}")

        # ── Endpoint 2: top players (a veces tiene xG) ──
        for metric in ["rating", "goals", "expectedGoals", "bigChancesCreated"]:
            ep = (
                f"https://api.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}"
                f"/season/{SEASON_ID}/top-players/{metric}"
            )
            try:
                page.goto(ep, wait_until="domcontentloaded", timeout=12000)
                page.wait_for_timeout(600)
            except Exception as e:
                print(f"  error top-players: {e}")

        # ── Endpoint 3: página web real de estadísticas del torneo ──
        try:
            print("Paso 2: navegando a la página de estadísticas del torneo...")
            page.goto(
                f"https://www.sofascore.com/football/tournament/chile/primera-division"
                f"/{TOURNAMENT_ID}#id:{SEASON_ID},tab:statistics,page:player",
                wait_until="domcontentloaded", timeout=25000,
            )
            page.wait_for_timeout(4000)
            # scroll para triggerear más carga
            page.evaluate("window.scrollTo(0, 600)")
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  error navegando torneo: {e}")

        browser.close()

    print(f"\n{'='*60}")
    print(f"Endpoints interceptados: {len(api_responses)}")

    # ── Parsear: buscar listas de jugadores con stats ──
    players_raw = []

    for key, raw in api_responses.items():
        # Formato 1: {"results": [...]} con player + statistics por entrada
        results = raw.get("results", raw.get("topPlayers", raw.get("players", [])))
        if not isinstance(results, list):
            continue
        for row in results:
            # Cada fila puede tener un jugador directamente o anidado
            player_obj = row.get("player", row)
            team_obj   = row.get("team", player_obj.get("team", {}))
            stats      = row.get("statistics", row)

            pid   = player_obj.get("id")
            pname = player_obj.get("name", player_obj.get("shortName", "?"))
            tname = team_obj.get("name", "?") if isinstance(team_obj, dict) else "?"
            tid   = team_obj.get("id")     if isinstance(team_obj, dict) else None

            if not pid or pname == "?":
                continue

            entry = {
                "player_id": pid, "player_name": pname,
                "team": tname,    "team_id": tid,
                "source_key": key[:60],
            }
            for f in PLAYER_FIELDS:
                v = stats.get(f)
                if v is not None:
                    entry[f] = v

            if any(f in entry for f in ["expectedGoals", "goals", "rating"]):
                players_raw.append(entry)

    # Deduplicar por player_id (quedarse con el que tenga más campos)
    best = {}
    for p in players_raw:
        pid = p["player_id"]
        if pid not in best or len(p) > len(best[pid]):
            best[pid] = p
    players = list(best.values())

    print(f"Jugadores únicos con datos: {len(players)}")
    has_xg = [p for p in players if p.get("expectedGoals") is not None]
    print(f"Con xG: {len(has_xg)}")

    # ── Agrupar por equipo ──
    teams = {}
    for p in players:
        tname = p["team"]
        tid   = p.get("team_id")
        t = teams.setdefault(tname, {
            "team": tname, "team_id": tid,
            "players": 0,
            "xG_total": 0.0, "xA_total": 0.0,
            "bigChancesCreated": 0, "bigChancesMissed": 0,
            "goals": 0, "assists": 0,
            "shotsOnTarget": 0, "shotsOffTarget": 0,
        })
        t["players"] += 1
        for f, key in [
            ("expectedGoals",    "xG_total"),
            ("expectedAssists",  "xA_total"),
            ("bigChancesCreated","bigChancesCreated"),
            ("bigChancesMissed", "bigChancesMissed"),
            ("goals",            "goals"),
            ("goalAssist",       "assists"),
            ("shotsOnTarget",    "shotsOnTarget"),
            ("shotsOffTarget",   "shotsOffTarget"),
        ]:
            if p.get(f) is not None:
                t[key] = round(t[key] + p[f], 3)

    team_list = sorted(teams.values(), key=lambda x: x["xG_total"], reverse=True)

    print(f"\nEquipos encontrados: {len(team_list)}")
    print(f"{'Equipo':<28} {'xG':>6} {'xA':>6} {'BCC':>4} {'BCM':>4} {'Goles':>5} {'Players':>7}")
    print("-" * 65)
    for t in team_list:
        print(f"{t['team']:<28} {t['xG_total']:>6.2f} {t['xA_total']:>6.2f} "
              f"{t['bigChancesCreated']:>4} {t['bigChancesMissed']:>4} "
              f"{t['goals']:>5} {t['players']:>7}")

    result = {
        "teams":    team_list,
        "players":  players,
        "_raw_keys": list(api_responses.keys()),
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nGuardado en {output_path}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    scrape(args.output)
