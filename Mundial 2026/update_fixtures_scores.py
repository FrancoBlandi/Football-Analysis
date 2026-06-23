#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_fixtures_scores.py — Actualiza los scores de los fixtures del Mundial desde SofaScore.
Requiere Chrome con --remote-debugging-port=9222 --remote-allow-origins=*
"""
import json, time, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FIXTURES_PATH = Path(__file__).parent / "wc2026_fixtures.json"
BASE = "https://www.sofascore.com/api/v1"
_XRW = "441959"


def setup(pw):
    global _XRW
    browser = pw.chromium.connect_over_cdp("http://localhost:9222", timeout=30000)
    ctx  = browser.contexts[0]
    page = ctx.new_page()

    captured = {}
    def on_req(req):
        if "/api/v1/player/" in req.url and "img." not in req.url:
            h = dict(req.headers)
            xrw = h.get("x-requested-with", "")
            if xrw and xrw != "441959":
                captured["v"] = xrw
    page.on("request", on_req)
    page.goto("https://www.sofascore.com/football/player/erling-haaland/839956",
              wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(4000)
    page.evaluate("(() => { var b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Matches'); if(b)b.click(); })()")
    page.wait_for_timeout(2000)
    page.remove_listener("request", on_req)

    _XRW = captured.get("v", "441959")
    print(f"x-requested-with: {_XRW}")
    return browser, page


def fetch(page, url):
    xrw = _XRW.replace("'", "\\'")
    try:
        result = page.evaluate(f"""(async () => {{
            const r = await fetch('{url}', {{
                credentials: 'include',
                headers: {{'x-requested-with': '{xrw}', 'Accept': 'application/json'}}
            }});
            return await r.text();
        }})()""")
        return json.loads(result) if result else None
    except Exception as e:
        print(f"  error: {e}")
        return None


def main():
    from playwright.sync_api import sync_playwright

    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures_data = json.load(f)

    fixtures = fixtures_data.get("fixtures", [])
    print(f"Fixtures a actualizar: {len(fixtures)}")

    with sync_playwright() as pw:
        browser, page = setup(pw)

        # Test
        test = fetch(page, f"{BASE}/event/15186710")
        if test and test.get("event"):
            e = test["event"]
            print(f"Test OK: {e.get('homeTeam',{}).get('name')} {e.get('homeScore',{}).get('current')}-{e.get('awayScore',{}).get('current')} {e.get('awayTeam',{}).get('name')}\n")
        else:
            print("ERROR: API no responde")
            browser.close()
            return

        updated = 0
        for i, fx in enumerate(fixtures, 1):
            eid = fx.get("event_id")
            if not eid:
                continue

            data = fetch(page, f"{BASE}/event/{eid}")
            if not data or not data.get("event"):
                time.sleep(0.3)
                continue

            e = data["event"]
            status_desc = e.get("status", {}).get("description", "")
            status_type = e.get("status", {}).get("type", "")

            sh = e.get("homeScore", {}).get("current")
            sa = e.get("awayScore", {}).get("current")

            fx["status"] = status_desc
            if status_type == "finished" and sh is not None and sa is not None:
                fx["score_home"] = sh
                fx["score_away"] = sa
                updated += 1
                home = e.get("homeTeam", {}).get("name", "?")
                away = e.get("awayTeam", {}).get("name", "?")
                print(f"  [{i}] {home} {sh}-{sa} {away} ✓")
            else:
                print(f"  [{i}] {e.get('homeTeam',{}).get('name','?')} vs {e.get('awayTeam',{}).get('name','?')} — {status_desc}")

            time.sleep(0.3 + (0.2 if i % 10 == 0 else 0))

        browser.close()

    with open(FIXTURES_PATH, "w", encoding="utf-8") as f:
        json.dump(fixtures_data, f, ensure_ascii=False, indent=2)

    print(f"\nListo. {updated} partidos con resultado guardados.")


if __name__ == "__main__":
    main()
