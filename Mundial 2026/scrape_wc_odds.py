#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_odds.py — Cuotas 1X2 del Mundial 2026 desde The Odds API

Uso:
    python "Mundial 2026/scrape_wc_odds.py" --key TU_API_KEY

Output: wc2026_odds.json
  { event_id_sofa: { "home": str, "away": str, "odds_1x2": {"home": float, "draw": float, "away": float} } }
"""

import json, sys, io, argparse, urllib.request, urllib.parse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT_PATH      = Path(__file__).parent / "wc2026_odds.json"
FIXTURES_PATH = Path(__file__).parent / "wc2026_fixtures.json"
BASE          = "https://api.the-odds-api.com/v4"

# Nombre de equipo: mapeo de The Odds API → nuestros nombres internos
TEAM_MAP = {
    "Argentina":              "Argentina",
    "Australia":              "Australia",
    "Belgium":                "Belgium",
    "Bolivia":                "Bolivia",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Brazil":                 "Brazil",
    "Cameroon":               "Cameroon",
    "Canada":                 "Canada",
    "Chile":                  "Chile",
    "China PR":               "China",
    "Colombia":               "Colombia",
    "Croatia":                "Croatia",
    "Curaçao":                "Curaçao",
    "Curaçao":                "Curaçao",
    "Czech Republic":         "Czechia",
    "Czechia":                "Czechia",
    "DR Congo":               "DR Congo",
    "Ecuador":                "Ecuador",
    "Egypt":                  "Egypt",
    "England":                "England",
    "France":                 "France",
    "Germany":                "Germany",
    "Ghana":                  "Ghana",
    "Haiti":                  "Haiti",
    "Indonesia":              "Indonesia",
    "Iran":                   "Iran",
    "Iraq":                   "Iraq",
    "Japan":                  "Japan",
    "Jordan":                 "Jordan",
    "Mexico":                 "Mexico",
    "Morocco":                "Morocco",
    "Netherlands":            "Netherlands",
    "New Zealand":            "New Zealand",
    "Nigeria":                "Nigeria",
    "Norway":                 "Norway",
    "Panama":                 "Panama",
    "Paraguay":               "Paraguay",
    "Portugal":               "Portugal",
    "Qatar":                  "Qatar",
    "Saudi Arabia":           "Saudi Arabia",
    "Scotland":               "Scotland",
    "Senegal":                "Senegal",
    "South Africa":           "South Africa",
    "South Korea":            "South Korea",
    "Spain":                  "Spain",
    "Switzerland":            "Switzerland",
    "Turkey":                 "Türkiye",
    "Türkiye":                "Türkiye",
    "United States":          "USA",
    "USA":                    "USA",
    "Uruguay":                "Uruguay",
    "Uzbekistan":             "Uzbekistan",
    "Ivory Coast":            "Côte d'Ivoire",
    "Côte d'Ivoire":          "Côte d'Ivoire",
    "Cabo Verde":             "Cabo Verde",
    "Cape Verde":             "Cabo Verde",
    "Algeria":                "Algeria",
    "Austria":                "Austria",
    "Sweden":                 "Sweden",
}


def api_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def find_sport_key(api_key):
    """Busca el sport key del Mundial 2026."""
    sports = api_get(f"{BASE}/sports/?apiKey={api_key}")
    wc = [s for s in sports if "fifa_world_cup" in s.get("key","").lower() and "winner" not in s.get("key","").lower()]
    for s in wc:
        print(f"  {s['key']} — {s['title']} (active={s.get('active')})")
    return wc


def fetch_odds(api_key, sport_key):
    """Descarga cuotas 1X2 en formato decimal, región EU (incluye Pinnacle, Bet365)."""
    params = urllib.parse.urlencode({
        "apiKey":      api_key,
        "regions":     "eu",
        "markets":     "h2h",
        "oddsFormat":  "decimal",
        "bookmakers":  "pinnacle,bet365,betfair,williamhill",
    })
    url = f"{BASE}/sports/{sport_key}/odds/?{params}"
    print(f"Fetching: {url[:80]}...")
    return api_get(url)


def best_h2h(bookmakers, home_name, away_name):
    """Promedia las cuotas de las casas disponibles buscando por nombre de equipo."""
    home_odds, draw_odds, away_odds = [], [], []
    for bk in bookmakers:
        for mkt in bk.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
            h = outcomes.get(home_name)
            d = outcomes.get("Draw")
            a = outcomes.get(away_name)
            if h and d and a:
                home_odds.append(h)
                draw_odds.append(d)
                away_odds.append(a)
    if not home_odds:
        return None
    avg = lambda lst: round(sum(lst) / len(lst), 3)
    return {"home": avg(home_odds), "draw": avg(draw_odds), "away": avg(away_odds)}


def normalize(name):
    return TEAM_MAP.get(name, name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, help="API key de the-odds-api.com")
    parser.add_argument("--sport", default=None, help="Sport key (auto-detect si no se especifica)")
    args = parser.parse_args()

    # Cargar fixtures para hacer matching por nombre de equipo
    fixtures = []
    if FIXTURES_PATH.exists():
        fx_data = json.load(open(FIXTURES_PATH, encoding="utf-8"))
        fixtures = fx_data.get("fixtures", [])
    fixture_index = {}
    for fx in fixtures:
        key = (normalize(fx["home_name"]), normalize(fx["away_name"]))
        fixture_index[key] = fx["event_id"]

    # Detectar sport key
    sport_key = args.sport
    if not sport_key:
        print("Buscando sport key del Mundial 2026...")
        sports = find_sport_key(args.key)
        if not sports:
            print("No se encontró sport key. Especificá uno con --sport")
            return
        sport_key = sports[0]["key"]
        print(f"Usando: {sport_key}\n")

    # Descargar cuotas
    events = fetch_odds(args.key, sport_key)
    print(f"Eventos recibidos: {len(events)}\n")

    result = {}
    unmatched = []

    for ev in events:
        home_raw = ev.get("home_team", "")
        away_raw = ev.get("away_team", "")
        home = normalize(home_raw)
        away = normalize(away_raw)

        odds = best_h2h(ev.get("bookmakers", []), home_raw, away_raw)
        if not odds:
            continue

        # Buscar event_id en nuestros fixtures
        event_id = fixture_index.get((home, away)) or fixture_index.get((away, home))

        entry = {
            "home":     home,
            "away":     away,
            "odds_1x2": odds,
            "event_id": event_id,
        }

        key = event_id or f"{home}_vs_{away}"
        result[str(key)] = entry

        status = f"✓ id={event_id}" if event_id else "? sin match"
        print(f"  {home} vs {away}  H={odds['home']}  D={odds['draw']}  A={odds['away']}  {status}")
        if not event_id:
            unmatched.append(f"{home_raw} vs {away_raw}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado: {OUT_PATH}  ({len(result)} partidos)")
    if unmatched:
        print(f"Sin match en fixtures ({len(unmatched)}): {unmatched}")

    # Mostrar requests restantes
    try:
        info = api_get(f"{BASE}/sports/?apiKey={args.key}")
        print(f"(requests usados hasta ahora, revisar en el dashboard de the-odds-api.com)")
    except:
        pass


if __name__ == "__main__":
    main()
