#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_wc_form_v4.py — Usa Chrome real via CDP con token x-captcha.
Requiere Chrome abierto con: --remote-debugging-port=9222

Uso:
    python scrape_wc_form_v4.py
"""

import json, time, random, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PLAYER_STATS_PATH = Path(__file__).parent / "wc2026_player_stats.json"
OUT_PATH          = Path(__file__).parent / "wc2026_form.json"
BASE              = "https://www.sofascore.com/api/v1"
N_MATCHES         = 10
DECAY             = 0.82
CDP_URL           = "http://localhost:9222"


def get_token_and_page(browser):
    """Extrae x-captcha token desde la tab de sofascore ya cargada."""
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()

    sofa_pages = [p for p in ctx.pages if "sofascore.com" in p.url and "player" in p.url]
    if not sofa_pages:
        sofa_pages = [p for p in ctx.pages if "sofascore.com" in p.url]

    page = sofa_pages[0] if sofa_pages else ctx.new_page()

    captured = {}
    def on_req(request):
        if "sofascore.com/api/v1/player" in request.url and "events/last" in request.url:
            captured.update(dict(request.headers))

    page.on("request", on_req)
    if not sofa_pages or "player" not in page.url:
        page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
    else:
        # La página ya está cargada — hacer un pequeño scroll para triggerear si falta
        page.wait_for_timeout(2000)
        page.evaluate("window.scrollTo(0, 100)")
        page.wait_for_timeout(2000)
    page.remove_listener("request", on_req)

    # Si no capturamos token, navegar a Kane
    if not captured.get("x-captcha"):
        page.on("request", on_req)
        page.goto("https://www.sofascore.com/football/player/harry-kane/108579",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        page.remove_listener("request", on_req)

    return page, captured.get("x-captcha", ""), captured.get("x-requested-with", "441959")


def api_call(page, url, xcaptcha, xrequested):
    """Hace una llamada a la API desde dentro de Chrome con el token."""
    escaped_captcha = xcaptcha.replace("'", "\\'")
    result = page.evaluate(f"""async () => {{
        try {{
            const r = await fetch('{url}', {{
                credentials: 'include',
                headers: {{
                    'x-captcha': '{escaped_captcha}',
                    'x-requested-with': '{xrequested}',
                    'Accept': 'application/json'
                }}
            }});
            return await r.text();
        }} catch(e) {{ return JSON.stringify({{error: e.toString()}}); }}
    }}""")
    try:
        return json.loads(result)
    except:
        return None


def scrape_player(page, player_id, national_team_id, xcaptcha, xrequested):
    all_events = []
    for pg in range(5):
        data = api_call(page, f"{BASE}/player/{player_id}/events/last/{pg}", xcaptcha, xrequested)
        if not data or not data.get("events"):
            break
        all_events.extend(data["events"])
        if not data.get("hasNextPage", False):
            break
        time.sleep(0.3)

    intl_events = [
        e for e in all_events
        if e.get("homeTeam", {}).get("id") == national_team_id
        or e.get("awayTeam", {}).get("id") == national_team_id
    ]
    intl_events.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)

    matches = []
    for ev in intl_events[:N_MATCHES * 3]:
        if len(matches) >= N_MATCHES:
            break
        eid = ev.get("id")
        if not eid:
            continue

        sdata = api_call(page, f"{BASE}/event/{eid}/player/{player_id}/statistics", xcaptcha, xrequested)
        st = (sdata or {}).get("statistics", {})
        mins = st.get("minutesPlayed") or 0
        if mins == 0:
            time.sleep(0.2)
            continue

        xg_direct = st.get("expectedGoals")
        goals_raw = st.get("goals") or 0
        xg = xg_direct if xg_direct is not None else max((st.get("totalShots") or 0) * 0.095, goals_raw * 0.5)
        xa_direct = st.get("expectedAssists")
        xa = xa_direct if xa_direct is not None else (st.get("keyPass") or 0) * 0.08

        matches.append({
            "event_id":   eid,
            "timestamp":  ev.get("startTimestamp"),
            "tournament": ev.get("tournament", {}).get("name", ""),
            "rating":     st.get("rating"),
            "mins":       mins,
            "xg":         round(xg, 4),
            "xa":         round(xa, 4),
            "goals":      goals_raw,
            "assists":    st.get("goalAssist") or 0,
        })
        time.sleep(0.4 + random.random() * 0.3)

    return matches


def form_stats(matches):
    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        if (m.get("mins") or 0) < 20:
            continue
        w = DECAY ** i
        w_xg    += (m["xg"] / m["mins"] * 90) * w
        w_xa    += (m["xa"] / m["mins"] * 90) * w
        total_w += w
    if total_w == 0:
        return None
    return {
        "form_xg_90": round(w_xg / total_w, 4),
        "form_xa_90": round(w_xa / total_w, 4),
        "n": len([m for m in matches if (m.get("mins") or 0) >= 20]),
    }


def save(existing, out_path):
    tmp = out_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    tmp.replace(out_path)


def main():
    player_stats = json.load(open(PLAYER_STATS_PATH, encoding="utf-8"))
    existing = json.load(open(OUT_PATH, encoding="utf-8")) if OUT_PATH.exists() else {}

    to_retry = {
        pid: p for pid, p in player_stats.items()
        if pid in existing and not (existing[pid] or {}).get("matches")
    }
    print(f"A recuperar: {len(to_retry)} jugadores\n")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        print("Conectando a Chrome...", flush=True)
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        page, xcaptcha, xrequested = get_token_and_page(browser)
        print(f"Token OK — expira en ~60min | x-requested-with: {xrequested}\n")

        # Test
        test = api_call(page, f"{BASE}/player/108579/events/last/0", xcaptcha, xrequested)
        if not test or test.get("error"):
            print(f"ERROR: {test}")
            return
        print(f"API OK — Kane: {len(test.get('events', []))} eventos\n")

        updated = 0
        consecutive_empty = 0
        token_refresh_counter = 0

        for i, (pid_str, pdata) in enumerate(to_retry.items(), 1):
            # Refrescar token cada 50 jugadores (el token dura ~60 min)
            token_refresh_counter += 1
            if token_refresh_counter > 50:
                print("\n--- Refrescando token ---", flush=True)
                page, xcaptcha, xrequested = get_token_and_page(browser)
                token_refresh_counter = 0
                time.sleep(2)

            name   = pdata.get("name", "?")
            team   = pdata.get("national_team", "?")
            nat_id = pdata.get("national_team_id")
            print(f"[{i}/{len(to_retry)}] {name} ({team})", end=" ", flush=True)

            if not nat_id:
                print("sin nat_id")
                continue

            matches = scrape_player(page, int(pid_str), nat_id, xcaptcha, xrequested)

            if matches:
                ratings = [m["rating"] for m in matches if m.get("rating") is not None]
                avg_r_str = f"{sum(ratings)/len(ratings):.2f}" if ratings else "N/A"
                print(f"→ {len(matches)} partidos | rating={avg_r_str}")
                existing[pid_str] = {
                    "name": name, "team": team,
                    "matches": matches, "form": form_stats(matches),
                }
                save(existing, OUT_PATH)
                updated += 1
                consecutive_empty = 0
            else:
                print("→ sin partidos")
                consecutive_empty += 1
                if consecutive_empty >= 60:
                    print("\n⚠ 60 vacíos consecutivos — posible rate limit. Parando.")
                    break

            time.sleep(1.2 + random.random() * 0.8)

    print(f"\nListo: {updated}/{len(to_retry)} recuperados")
    with_rating = sum(1 for fd in existing.values() if fd and any(m.get("rating") for m in fd.get("matches", [])))
    print(f"Total con rating: {with_rating}/{len(existing)}")


if __name__ == "__main__":
    main()
