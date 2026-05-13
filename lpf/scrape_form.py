#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_form.py — Últimos N partidos por jugador (SofaScore via Playwright)
Genera lpf/form_data.json con xG/xA recientes para ponderación de forma.

Uso:
    python lpf/scrape_form.py              # todos los jugadores de fixture clubs
    python lpf/scrape_form.py --test       # solo 5 jugadores para verificar
    python lpf/scrape_form.py --resume     # continúa desde donde quedó
"""

import json, time, random, argparse, sys
from pathlib import Path

JSON_PATH = Path(__file__).parent / "lpf_data.json"
OUT_PATH  = Path(__file__).parent / "form_data.json"
N_MATCHES = 5
DECAY     = 0.75

FIXTURE_CLUBS = {
    "CA Talleres", "Club Atlético Belgrano", "Boca Juniors", "Huracán",
    "Argentinos Juniors", "CA Lanús", "Independiente Rivadavia",
    "Club Atlético Unión de Santa Fe", "Rosario Central", "CA Independiente",
    "Estudiantes de La Plata", "Racing Club", "River Plate", "San Lorenzo",
    "Vélez Sarsfield", "Gimnasia y Esgrima",
}


def nav_json(page, url, retries=3):
    """Navega a una URL de API y parsea el JSON del body."""
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(600)
            text = page.evaluate("document.body.innerText")
            return json.loads(text)
        except json.JSONDecodeError:
            # Puede ser que la página devolvió HTML de error
            status_text = page.evaluate("document.body.innerText[:200]") if attempt < retries - 1 else ""
            if "429" in status_text or "rate" in status_text.lower():
                wait = 30 + attempt * 15
                print(f"    rate-limit detectado — esperando {wait}s…")
                time.sleep(wait)
            else:
                time.sleep(2 + attempt * 2)
        except Exception as e:
            print(f"    warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None


LPF_TOURNAMENT_ID   = 155    # Liga Profesional Argentina
APERTURA_2026_SEASON = 87913  # Season ID del Torneo Apertura 2026


def scrape_player_form(page, player_id, club_id=None):
    base = f"https://api.sofascore.com/api/v1/player/{player_id}"

    data = nav_json(page, f"{base}/events/last/0")
    if not data or "events" not in data:
        return []

    all_events = data["events"]
    lpf_events = []
    for e in all_events:
        if e.get("tournament", {}).get("uniqueTournament", {}).get("id") != LPF_TOURNAMENT_ID:
            continue
        # Solo partidos del Apertura 2026 (season_id exacto)
        if e.get("season", {}).get("id") != APERTURA_2026_SEASON:
            continue
        # Verificar que el jugador haya representado a su equipo actual en este partido
        if club_id:
            home_id = e.get("homeTeam", {}).get("id")
            away_id = e.get("awayTeam", {}).get("id")
            if home_id != club_id and away_id != club_id:
                continue
        lpf_events.append(e)

    # Ordenar de más reciente a más antiguo (la API no garantiza orden)
    # Tomamos hasta N_MATCHES*3 candidatos para poder saltar partidos sin minutos
    lpf_events.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
    candidates = lpf_events[:N_MATCHES * 3]
    matches = []

    for ev in candidates:
        if len(matches) >= N_MATCHES:
            break
        eid = ev.get("id")
        if not eid:
            continue

        sdata = nav_json(page, f"https://api.sofascore.com/api/v1/event/{eid}/player/{player_id}/statistics")
        stats = sdata.get("statistics", {}) if sdata else {}
        mins  = stats.get("minutesPlayed") or 0

        # Saltar partidos donde el jugador no entró (banco sin minutos)
        if mins == 0:
            time.sleep(0.2)
            continue

        # xG: usar dato directo si existe. Si no (Apertura 2026 aún sin procesar),
        # estimar por remates y usar goals como piso — un gol ≥ 0.5 xG (penal ~0.76).
        xg_direct = stats.get("expectedGoals")
        goals_raw  = stats.get("goals") or 0
        if xg_direct is not None:
            xg = xg_direct
        else:
            shots = stats.get("totalShots") or 0
            xg = max(shots * 0.095, goals_raw * 0.5)

        xa_direct  = stats.get("expectedAssists")
        if xa_direct is not None:
            xa = xa_direct
        else:
            # keyPass * 0.08 — mismo fallback que season stats cuando no hay xA directo
            key_passes = stats.get("keyPass") or 0
            xa = key_passes * 0.08

        matches.append({
            "event_id":  eid,
            "timestamp": ev.get("startTimestamp"),
            "rating":    stats.get("rating"),
            "mins":      mins,
            "xg":        round(xg, 4),
            "xa":        round(xa, 4),
            "xg_direct": xg_direct is not None,   # True si SofaScore proveyó xG real
            "goals":     stats.get("goals") or 0,
            "assists":   stats.get("goalAssist") or 0,
        })
        time.sleep(0.3 + random.random() * 0.3)

    return matches


def form_stats(matches):
    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        mins = m.get("mins") or 0
        if mins < 20:
            continue
        w = DECAY ** i
        w_xg    += (m["xg"] / mins * 90) * w
        w_xa    += (m["xa"] / mins * 90) * w
        total_w += w
    if total_w == 0:
        return None
    return {
        "form_xg_90": round(w_xg / total_w, 4),
        "form_xa_90": round(w_xa / total_w, 4),
        "n":          len([m for m in matches if (m.get("mins") or 0) >= 20]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",   action="store_true", help="Solo primeros 5 jugadores")
    parser.add_argument("--resume", action="store_true", help="Saltar jugadores ya procesados")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    with open(JSON_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    players = [
        p for p in raw["Primera LPF 2026"]
        if p.get("Club") in FIXTURE_CLUBS
        and (p.get("Minutos Jugados") or 0) >= 90
        and p.get("player_id")
    ]
    if args.test:
        players = players[:5]

    result = {}
    if OUT_PATH.exists() and args.resume:
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} jugadores ya procesados.")

    total = len(players)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Sesión inicial en sofascore.com (cookies)
        print("Iniciando sesión…")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        # Verificar conectividad con un jugador conocido
        test = nav_json(page, "https://api.sofascore.com/api/v1/player/255389/events/last/0")
        if not test or "events" not in test:
            print(f"ERROR: API no responde — {str(test)[:200]}")
            browser.close()
            return
        print(f"API OK — Paredes: {len(test['events'])} eventos recientes\n")

        for i, p in enumerate(players, 1):
            pid  = str(p["player_id"])
            name = p["Jugador"]

            if pid in result and args.resume:
                continue

            club_id = p.get("club_id")
            print(f"[{i}/{total}] {name} ({p['Club']})")
            matches = scrape_player_form(page, int(pid), club_id=club_id)
            stats   = form_stats(matches)

            if matches:
                n_ok = len([m for m in matches if (m.get("mins") or 0) >= 20])
                xg_vals = [round(m["xg"], 2) for m in matches]
                direct  = sum(1 for m in matches if m.get("xg_direct"))
                print(f"    {n_ok} partidos OK | xG últimos: {xg_vals} ({direct}/{len(matches)} con xG real)")

            result[pid] = {"name": name, "club": p["Club"], "matches": matches, "form": stats}

            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            time.sleep(0.8 + random.random() * 0.7)

        browser.close()

    print(f"\nListo. {len(result)} jugadores en {OUT_PATH}")
    with_form = [v for v in result.values() if v.get("form")]
    print(f"Con datos de forma: {len(with_form)}/{len(result)}")
    if with_form:
        top = sorted(with_form, key=lambda x: x["form"]["form_xg_90"], reverse=True)[:5]
        print("Top 5 xG/90 forma reciente:")
        for v in top:
            f = v["form"]
            print(f"  {v['name']:<28} xG/90={f['form_xg_90']}  xA/90={f['form_xa_90']}  n={f['n']}")


if __name__ == "__main__":
    main()
