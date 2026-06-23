#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_match_analytics.py — Scraping de analytics por partido para el modelo de predicción

Por cada selección, toma sus últimos MAX_EVENTS partidos competitivos y extrae:
  - Scoreline completo + score al HT (desde incidents)
  - Stats 1H/2H: shots, shots on target, big chances, possession
  - Odds 1X2 pre-partido (fractional → decimal → implícita)
  - Calidad del rival (FIFA rank del scraper ya existente)

Output: wc2026_match_analytics.json
  {
    "Argentina": {
      "team_id": 4819,
      "matches": [
        {
          "event_id": ...,
          "is_home": bool,
          "opponent": str,
          "opponent_fifa": int,
          "date": int (timestamp),
          "score_ft": [own, opp],
          "score_ht": [own, opp],   # null si no disponible
          "stats": {
            "ALL": {...}, "1ST": {...}, "2ND": {...}
          },
          "odds_1x2": {"home": float, "draw": float, "away": float},  # null si no hay
          "odds_ou": {"over": float, "under": float},   # null si no hay
          "btts": {"yes": float, "no": float},          # null si no hay
        },
        ...
      ]
    }
  }
"""

import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SQUADS_PATH   = Path(__file__).parent / "wc2026_squads.json"
OUT_PATH      = Path(__file__).parent / "wc2026_match_analytics.json"
COACHES_PATH  = Path(__file__).parent / "wc2026_coaches.json"

BASE          = "https://api.sofascore.com/api/v1"
MAX_EVENTS    = 20
FRIENDLY_IDS  = {313, 1108, 9596}

# FIFA rank de cada selección (para calcular calidad del rival)
FIFA_RANKINGS = {
    "Argentina": 100, "France": 95,  "Spain": 92,    "England": 88,
    "Brazil": 85,     "Portugal": 82, "Netherlands": 79, "Belgium": 76,
    "Germany": 74,    "Uruguay": 71,  "Colombia": 68, "Morocco": 65,
    "USA": 62,        "Croatia": 60,  "Switzerland": 58, "Japan": 56,
    "Senegal": 54,    "Mexico": 52,   "South Korea": 50, "Australia": 47,
    "Austria": 45,    "Algeria": 44,  "Norway": 41,   "Czechia": 39,
    "Ecuador": 38,    "Iran": 36,     "Iraq": 30,     "Canada": 35,
    "Egypt": 34,      "Scotland": 33, "Saudi Arabia": 38, "Tunisia": 31,
    "Sweden": 30,     "Ghana": 27,    "South Africa": 25,
    "Panama": 24,     "Paraguay": 23, "Cabo Verde": 35,
    "Côte d'Ivoire": 45, "Curaçao": 18, "New Zealand": 20,
    "DR Congo": 30,   "Haiti": 17,    "Jordan": 28,
    "Bosnia & Herzegovina": 35, "Qatar": 25, "Uzbekistan": 32,
    "Turkey": 38,
}

STAT_KEYS = [
    "Ball possession", "Total shots", "Shots on target", "Big chances",
    "Big chances scored", "Shots inside box", "Shots outside box",
    "Goalkeeper saves", "Corner kicks",
]


_XCAPTCHA    = ""
_XREQUESTED  = "441959"

def nav_json(page, url, retries=3):
    for attempt in range(retries):
        try:
            cap = _XCAPTCHA.replace("'", "\\'")
            xrq = _XREQUESTED
            result = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        credentials: 'include',
                        headers: {{
                            'x-captcha': '{cap}',
                            'x-requested-with': '{xrq}',
                            'Accept': 'application/json'
                        }}
                    }});
                    return await r.text();
                }} catch(e) {{ return JSON.stringify({{error: e.toString()}}); }}
            }}""")
            if not result:
                time.sleep(2)
                continue
            data = json.loads(result)
            if "error" in data and "events" not in data and "statistics" not in data:
                time.sleep(2 + attempt * 2)
                continue
            return data
        except json.JSONDecodeError:
            time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


def frac_to_decimal(frac_str):
    """'3/5' → 1.6  |  '11/10' → 2.1"""
    try:
        num, den = frac_str.split("/")
        return round(int(num) / int(den) + 1, 4)
    except Exception:
        return None


def get_events(page, team_id):
    events = []
    for pg in range(4):
        data = nav_json(page, f"{BASE}/team/{team_id}/events/last/{pg}")
        if not data or not data.get("events"):
            break
        events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.3)
    competitive = [
        e for e in events
        if (e.get("tournament", {}).get("uniqueTournament") or {}).get("id", 0)
           not in FRIENDLY_IDS
        and (e.get("status") or {}).get("type") == "finished"
    ]
    competitive.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
    return competitive[:MAX_EVENTS]


def get_period_stats(page, event_id):
    """Devuelve dict {period: {stat_name: (home_val, away_val)}} para ALL/1ST/2ND."""
    data = nav_json(page, f"{BASE}/event/{event_id}/statistics")
    if not data:
        return {}
    result = {}
    for period_block in data.get("statistics", []):
        period = period_block.get("period", "ALL")
        stats = {}
        for group in period_block.get("groups", []):
            for item in group.get("statisticsItems", []):
                name = item.get("name", "")
                if name in STAT_KEYS:
                    # possession viene como "63%" → int
                    def parse_val(v):
                        if v is None:
                            return None
                        v = str(v).replace("%", "").strip()
                        try:
                            return float(v)
                        except Exception:
                            return None
                    stats[name] = {
                        "home": parse_val(item.get("home")),
                        "away": parse_val(item.get("away")),
                    }
        result[period] = stats
    return result


def get_ht_score(page, event_id, home_id, team_id):
    """Intenta extraer score al HT desde incidents (primer gol antes del min 45+)."""
    data = nav_json(page, f"{BASE}/event/{event_id}/incidents")
    if not data:
        return None
    incidents = data.get("incidents", [])
    ht_home = 0
    ht_away = 0
    is_home = (home_id == team_id)
    for inc in incidents:
        if inc.get("incidentType") == "period" and inc.get("text") == "HT":
            break
        if inc.get("incidentType") in ("goal", "ownGoal") and inc.get("incidentClass") != "penalty":
            if inc.get("isHome"):
                ht_home += 1
            else:
                ht_away += 1
    # Convertir a perspectiva del equipo analizado
    own_ht = ht_home if is_home else ht_away
    opp_ht = ht_away if is_home else ht_home
    return [own_ht, opp_ht]


def get_odds(page, event_id):
    """Extrae odds 1X2, O/U 2.5, BTTS del evento."""
    data = nav_json(page, f"{BASE}/event/{event_id}/odds/1/all")
    if not data or data.get("error"):
        return None, None, None

    odds_1x2 = None
    odds_ou   = None
    odds_btts = None

    for market in data.get("markets", []):
        mg   = market.get("marketGroup", "")
        name = market.get("marketName", "")
        choices = {c["name"]: frac_to_decimal(c.get("fractionalValue", ""))
                   for c in market.get("choices", [])
                   if c.get("fractionalValue")}

        if mg == "1X2" and "Full time" in name and not market.get("isLive"):
            odds_1x2 = {
                "home": choices.get("1"),
                "draw": choices.get("X"),
                "away": choices.get("2"),
            }
        elif "2.5" in name and not market.get("isLive"):
            odds_ou = {
                "over":  choices.get("Over"),
                "under": choices.get("Under"),
            }
        elif "Both teams" in name and not market.get("isLive"):
            odds_btts = {
                "yes": choices.get("Yes"),
                "no":  choices.get("No"),
            }

    return odds_1x2, odds_ou, odds_btts


def main():
    from playwright.sync_api import sync_playwright

    squads = json.load(open(SQUADS_PATH, encoding="utf-8"))

    # Solo equipos con 26 jugadores confirmados
    teams = [
        (name, data["team_id"], data["group"])
        for name, data in squads.items()
        if len(data["players"]) == 26
    ]

    # Si existe resultado previo, retomar
    result = {}
    if OUT_PATH.exists():
        result = json.load(open(OUT_PATH, encoding="utf-8"))
        already = set(result.keys())
        teams = [(n, t, g) for n, t, g in teams if n not in already]
        print(f"Retomando: {len(already)} equipos ya procesados. Quedan {len(teams)}.\n")

    print(f"Equipos a procesar: {len(teams)}")

    with sync_playwright() as pw:
        CDP_URL = "http://localhost:9222"
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        ctx = browser.contexts[0]
        page = ctx.new_page()

        # Capturar x-captcha desde páginas SofaScore ya abiertas (mismo enfoque form_v4)
        sofa_pages = [p for p in ctx.pages if "sofascore.com" in p.url and "player" in p.url]
        if not sofa_pages:
            sofa_pages = [p for p in ctx.pages if "sofascore.com" in p.url]
        page = sofa_pages[0] if sofa_pages else ctx.new_page()

        captured = {}
        def on_req(request):
            if "sofascore.com/api/v1/player" in request.url and "events/last" in request.url:
                h = dict(request.headers)
                if h.get("x-captcha"):
                    captured.update(h)
        page.on("request", on_req)
        if not sofa_pages or "player" not in page.url:
            page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
        else:
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, 100)")
            page.wait_for_timeout(2000)
        page.remove_listener("request", on_req)

        if not captured.get("x-captcha"):
            page.on("request", on_req)
            page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            page.remove_listener("request", on_req)

        global _XCAPTCHA, _XREQUESTED
        _XCAPTCHA   = captured.get("x-captcha", "")
        _XREQUESTED = captured.get("x-requested-with", "441959")
        print(f"Chrome CDP | token={'OK ('+_XCAPTCHA[:12]+')' if _XCAPTCHA else 'MISSING'} | xrw={_XREQUESTED}")

        for i, (team_name, team_id, group) in enumerate(teams, 1):
            print(f"\n[{i}/{len(teams)}] [{group}] {team_name} (id={team_id})")
            events = get_events(page, team_id)
            print(f"  {len(events)} partidos competitivos")

            matches = []
            for ev in events:
                eid     = ev["id"]
                home_id = ev.get("homeTeam", {}).get("id")
                away_id = ev.get("awayTeam", {}).get("id")
                is_home = (home_id == team_id)
                opp_id  = away_id if is_home else home_id
                opp_name = (ev.get("awayTeam" if is_home else "homeTeam") or {}).get("name", "?")
                opp_fifa = FIFA_RANKINGS.get(opp_name, 40)

                score_h = (ev.get("homeScore") or {}).get("current")
                score_a = (ev.get("awayScore") or {}).get("current")
                if score_h is None or score_a is None:
                    continue
                own_ft = score_h if is_home else score_a
                opp_ft = score_a if is_home else score_h

                # Stats por periodo
                stats = get_period_stats(page, eid)
                time.sleep(0.2)

                # HT score desde incidents
                ht_score = get_ht_score(page, eid, home_id, team_id)
                time.sleep(0.2)

                # Odds
                odds_1x2, odds_ou, odds_btts = get_odds(page, eid)
                time.sleep(0.3)

                match_data = {
                    "event_id":    eid,
                    "is_home":     is_home,
                    "opponent":    opp_name,
                    "opponent_id": opp_id,
                    "opponent_fifa": opp_fifa,
                    "date":        ev.get("startTimestamp"),
                    "score_ft":    [own_ft, opp_ft],
                    "score_ht":    ht_score,
                    "stats":       stats,
                    "odds_1x2":    odds_1x2,
                    "odds_ou":     odds_ou,
                    "odds_btts":   odds_btts,
                }
                matches.append(match_data)

                has_stats  = bool(stats)
                has_odds   = odds_1x2 is not None
                has_ht     = ht_score is not None
                print(f"  {opp_name:<25} {own_ft}-{opp_ft}  stats={'Y' if has_stats else 'N'}  odds={'Y' if has_odds else 'N'}  ht={'Y' if has_ht else 'N'}")
                time.sleep(0.4)

            result[team_name] = {
                "team_id": team_id,
                "group":   group,
                "matches": matches,
            }

            # Guardar después de cada equipo
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            time.sleep(1.0)

        browser.close()

    print(f"\nGuardado: {OUT_PATH}")
    print(f"Equipos procesados: {len(result)}")


if __name__ == "__main__":
    main()
