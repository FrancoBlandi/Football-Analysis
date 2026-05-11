#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_injuries.py — Bajas confirmadas (lesiones + suspensiones) para los equipos del fixture.

Estrategia en dos pasos:
  1. SofaScore API: missing-players por evento (funciona ~24-48h antes del partido)
  2. Fallback: búsqueda en Google de "[equipo] lesionados suspendidos" + parseo de snippets

Uso:
    python lpf/scrape_injuries.py
"""

import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LPF_DATA_PATH  = Path(__file__).parent / "lpf_data.json"
FM_MAPPED_PATH = Path(__file__).parent / "fm_mapped.json"

# ── Equipos del fixture actual — actualizar en cada fase ────────────────────
FIXTURE_TEAMS = {
    "Club Atlético Belgrano":           ("belgrano",           3203),
    "Club Atlético Unión de Santa Fe":  ("union-santa-fe",     3204),
    "Argentinos Juniors":               ("argentinos-juniors", 3216),
    "Huracán":                          ("huracan",            7629),
    "Rosario Central":                  ("rosario-central",    3217),
    "Racing Club":                      ("racing-club",        3215),
    "River Plate":                      ("river-plate",        3211),
    "Gimnasia y Esgrima":               ("gimnasia-la-plata",  3205),
}

PHASE_LABEL   = "Cuartos de Final — Apertura 2026"
NEWS_SINCE    = "2026-05-01"   # filtro Google News RSS — ajustar al inicio de cada fase


# ────────────────────────────────────────────────────────────────────────────

def nav_json(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(700)
    try:
        return json.loads(page.evaluate("document.body.innerText"))
    except Exception:
        return {}


def fetch_missing_players_api(page, team_id):
    """Intenta SofaScore missing-players via API del próximo evento."""
    data = nav_json(page, f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0")
    events = data.get("events", [])
    if not events:
        return None, []

    event_id = events[0].get("id")
    home_name = events[0].get("homeTeam", {}).get("name", "?")
    away_name = events[0].get("awayTeam", {}).get("name", "?")
    home_id   = events[0].get("homeTeam", {}).get("id")
    away_id   = events[0].get("awayTeam", {}).get("id")

    mdata = nav_json(page, f"https://api.sofascore.com/api/v1/event/{event_id}/missing-players")
    if "error" in mdata:
        return f"{home_name} vs {away_name}", None   # None = endpoint no listo

    result = []
    for side, side_id in [("home", home_id), ("away", away_id)]:
        if side_id != team_id:
            continue
        for entry in mdata.get(side, {}).get("missingPlayers", []):
            p = entry.get("player", {})
            result.append({
                "ss_id":  p.get("id"),
                "name":   p.get("name") or p.get("shortName", "?"),
                "reason": entry.get("type") or entry.get("reason", ""),
            })
    return f"{home_name} vs {away_name}", result


def search_injuries(team_display, phase_label):
    """
    Busca en Google News RSS '[equipo] lesionados suspendidos [fase]'.
    RSS público sin bot detection. Devuelve lista de títulos de noticias recientes.
    """
    import urllib.parse, urllib.request, xml.etree.ElementTree as ET

    # Nombre corto del equipo para la query (sin "Club Atlético", etc.)
    short = (team_display
             .replace("Club Atlético ", "")
             .replace("Club Atlético", "")
             .replace("Gimnasia y Esgrima", "Gimnasia La Plata"))
    query = f'"{short}" lesion OR suspendido OR baja after:{NEWS_SINCE}'
    url   = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=es-419&gl=AR&ceid=AR:es"
    req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_bytes = resp.read()
    except Exception as e:
        return [f"(error búsqueda: {e})"]

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ["(error parseando RSS)"]

    items = root.findall(".//item")
    results = []
    for item in items[:8]:
        title = (item.findtext("title") or "").strip()
        if title:
            results.append(title)
    return results


def load_lpf_players():
    with open(LPF_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    players = []
    for season_data in data.values():
        players.extend(season_data)
    return {p["player_id"]: p for p in players if p.get("player_id")}


def load_fm_mapped():
    with open(FM_MAPPED_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    from playwright.sync_api import sync_playwright

    lpf_players = load_lpf_players()
    fm_mapped   = load_fm_mapped()

    print("=" * 65)
    print(f"BAJAS — {PHASE_LABEL}")
    print("=" * 65)

    api_results   = {}   # team → list of {ss_id, name, reason}
    news_snippets = {}   # team → list of str

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "es-AR,es;q=0.9",
        })

        for team_name, (slug, team_id) in FIXTURE_TEAMS.items():
            print(f"\n{'─'*55}")
            print(f"  {team_name}")
            print(f"{'─'*55}")

            # Paso 1: SofaScore API
            match_label, api_missing = fetch_missing_players_api(page, team_id)
            time.sleep(0.8)

            if api_missing is None:
                # Endpoint 404 → todavía no está disponible → buscar en noticias
                print(f"  SofaScore missing-players: no disponible aún")
                print(f"  → Buscando noticias en Google…")
                snippets = search_injuries(team_name, PHASE_LABEL)
                news_snippets[team_name] = snippets
                api_results[team_name]   = []
                if snippets:
                    for s in snippets:
                        print(f"    · {s[:110]}")
                else:
                    print(f"    (sin resultados relevantes)")
            elif not api_missing:
                print(f"  SofaScore ({match_label}): sin bajas registradas")
                api_results[team_name] = []
            else:
                print(f"  SofaScore ({match_label}): {len(api_missing)} baja(s)")
                api_results[team_name] = api_missing
                for p in api_missing:
                    ss_id = p["ss_id"]
                    in_lpf = ss_id in lpf_players if ss_id else False
                    fm_info = fm_mapped.get(str(ss_id), {}) if ss_id else {}
                    fm_name = fm_info.get("fm_name", "—")
                    tag = "✓ en analytics" if in_lpf else "✗ no en analytics"
                    print(f"  ⚠  {p['name']:<28} [{p['reason']}]  ss_id={ss_id}  {tag}  fm={fm_name}")

            time.sleep(1.0)

        browser.close()

    # Resumen final
    print("\n" + "=" * 65)
    print("RESUMEN — candidatos para EXCLUDED_PLAYER_IDS:")
    print("=" * 65)

    any_api = False
    for team_name, missing in api_results.items():
        relevant = [p for p in missing if p.get("ss_id") and p["ss_id"] in lpf_players]
        if relevant:
            any_api = True
            print(f"\n  # {team_name}")
            for p in relevant:
                reason = (p.get("reason") or "baja").strip()
                print(f"  {p['ss_id']},   # {p['name']} ({reason})")

    if news_snippets:
        print("\n  ── Revisar manualmente (Google snippets) ──")
        for team, snippets in news_snippets.items():
            if snippets:
                print(f"\n  {team}:")
                for s in snippets[:5]:
                    print(f"    {s[:100]}")

    if not any_api and not any(news_snippets.values()):
        print("\n  Sin bajas detectadas.")
    elif not any_api:
        print("\n  (SofaScore no detectó bajas en analytics — revisar snippets arriba)")


if __name__ == "__main__":
    main()
