import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def fetch_json(page, url):
    r = page.evaluate(f"""
        async () => {{
            const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
            if (!resp.ok) return {{}};
            return await resp.json();
        }}
    """)
    return r or {}

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36").new_page()
    page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1000)
    # J4 Danubio vs Progreso (known autogoles by Kidd and Costantino)
    data = fetch_json(page, "https://api.sofascore.com/api/v1/event/15523841/incidents")
    browser.close()

for inc in data.get('incidents', []):
    if inc.get('incidentType') in ('goal', 'penaltyScored', 'ownGoal'):
        print(json.dumps({k: inc.get(k) for k in
            ['incidentType', 'isHome', 'time', 'incidentClass',
             'player', 'assist1', 'homeScore', 'awayScore']},
            ensure_ascii=False))
