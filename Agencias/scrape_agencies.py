#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_agencies.py — Scrape player rosters for each agency from Transfermarkt.

Para cada agencia en agencies.json visita su perfil en TM y extrae:
  - Jugadores representados: nombre, tm_id, club, valor de mercado,
    vencimiento de contrato, posición, nacionalidad

Output: Agencias/agency_rosters.json

Uso:
    python Agencias/scrape_agencies.py
    python Agencias/scrape_agencies.py --resume
"""

import json, time, random, argparse, sys, re
from pathlib import Path
from bs4 import BeautifulSoup

AGENCIES_PATH = Path(__file__).parent / "agencies.json"
OUT_PATH      = Path(__file__).parent / "agency_rosters.json"

BASE_URL = "https://www.transfermarkt.us"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}


def nav_html(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200 + random.randint(0, 800))
            return page.content()
        except Exception as e:
            print(f"  warn ({attempt+1}/{retries}): {e}")
            time.sleep(4 + attempt * 3)
    return None


def parse_market_value(txt):
    if not txt:
        return None
    txt = txt.strip().replace("\xa0", "").replace(",", ".")
    m = re.search(r"([\d.]+)\s*(m|k|Th\.)?", txt, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit in ("m",):
        return round(val * 1_000_000)
    if unit in ("k", "th."):
        return round(val * 1_000)
    return round(val)


def find_tm_id(page, slug):
    """Busca el TM ID de una agencia por slug via search."""
    url  = f"{BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={slug.replace('-', '+')}&Berater_page=1"
    html = nav_html(page, url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/beraterfirma/berater/\d+")):
        m = re.search(r"/berater/(\d+)", a.get("href", ""))
        if m:
            return int(m.group(1))
    return None


def scrape_agency_roster(page, agency):
    tm_id = agency.get("tm_id")
    slug  = agency.get("slug", "agency")

    # Intentar encontrar tm_id si no lo tenemos
    if not tm_id:
        print(f"  Buscando tm_id para {agency['name']}...", end=" ")
        tm_id = find_tm_id(page, slug)
        if tm_id:
            agency["tm_id"] = tm_id
            print(f"encontrado: {tm_id}")
        else:
            print("no encontrado, saltando.")
            return []

    players = []
    page_num = 1

    while True:
        url  = f"{BASE_URL}/{slug}/beraterfirma/berater/{tm_id}/page/{page_num}"
        html = nav_html(page, url)
        if not html:
            break

        soup  = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="items")
        if not table:
            if page_num == 1:
                print(f"  No se encontro tabla para {agency['name']}")
            break

        rows = table.find("tbody").find_all("tr", recursive=False) if table.find("tbody") else []
        if not rows:
            break

        for row in rows:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 5:
                continue

            # Nombre + posicion (dentro de inline-table)
            inline = row.find("table", class_="inline-table")
            if not inline:
                continue
            a_tag = inline.find("a", href=re.compile(r"/spieler/\d+"))
            if not a_tag:
                continue

            player_name  = a_tag.get_text(strip=True)
            href         = a_tag.get("href", "")
            tm_player_id = None
            m = re.search(r"/spieler/(\d+)", href)
            if m:
                tm_player_id = int(m.group(1))

            # Posicion (segunda fila del inline-table)
            pos_tds = inline.find_all("td")
            pos = pos_tds[-1].get_text(strip=True) if len(pos_tds) > 1 else ""

            # Nacionalidad (img con title)
            nat_img = cells[1].find("img") if len(cells) > 1 else None
            nationality = nat_img.get("title", "") if nat_img else ""

            # Edad
            age_txt = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            # Club (img con title en cells[3])
            club_img  = cells[3].find("img") if len(cells) > 3 else None
            club_name = club_img.get("title", "") if club_img else ""

            # Vencimiento contrato
            contract = cells[4].get_text(strip=True) if len(cells) > 4 else ""

            # Valor de mercado (ultima celda con clase hauptlink)
            mv_cell = row.find("td", class_="hauptlink zentriert") or \
                      (cells[-1] if cells else None)
            mv_txt  = mv_cell.get_text(strip=True) if mv_cell else ""
            mv      = parse_market_value(mv_txt)

            players.append({
                "name":             player_name,
                "tm_id":            tm_player_id,
                "tm_url":           f"{BASE_URL}{href}" if href else None,
                "nationality":      nationality,
                "age":              age_txt,
                "club":             club_name,
                "contract_end":     contract,
                "market_value":     mv,
                "market_value_raw": mv_txt,
                "position":         pos,
                "agency":           agency["name"],
            })

        # Verificar si hay pagina siguiente
        next_link = soup.find("li", class_="naechste-seite")
        if not next_link or not next_link.find("a"):
            break
        page_num += 1
        time.sleep(1.5 + random.random())

    return players


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("pip install playwright beautifulsoup4 && playwright install chromium")

    with open(AGENCIES_PATH, encoding="utf-8") as f:
        agencies = json.load(f)

    result = {}
    if OUT_PATH.exists() and args.resume:
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} agencias ya procesadas.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
        )
        page = ctx.new_page()

        print("Conectando a Transfermarkt...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        total = len(agencies)
        for i, agency in enumerate(agencies, 1):
            name = agency["name"]
            if args.resume and name in result:
                print(f"[{i}/{total}] {name} — ya procesada, saltando.")
                continue

            print(f"[{i}/{total}] {name}...", end=" ")
            players = scrape_agency_roster(page, agency)
            result[name] = {
                "tm_id":   agency.get("tm_id"),
                "players": players,
                "n":       len(players),
            }
            print(f"{len(players)} jugadores")

            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            time.sleep(2 + random.random() * 2)

        browser.close()

    # Resumen
    total_players = sum(v["n"] for v in result.values())
    print(f"\nListo. {len(result)} agencias | {total_players} jugadores en total.")
    print(f"Output: {OUT_PATH}")

    with_mv = sum(
        1 for v in result.values()
        for p in v["players"] if p.get("market_value")
    )
    print(f"Jugadores con valor de mercado: {with_mv}/{total_players}")


if __name__ == "__main__":
    main()
