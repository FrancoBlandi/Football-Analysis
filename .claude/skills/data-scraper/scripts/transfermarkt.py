"""
transfermarkt.py — Scraper de plantel desde Transfermarkt

Uso:
    python transfermarkt.py --club-id 1029 --output plantel_tm.json

Dependencias:
    pip install requests beautifulsoup4
"""

import argparse
import io
import json
import re
import sys
from datetime import date

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'es-AR,es;q=0.9',
    'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.google.com/',
}

CLUBS = {
    1029: 'Velez Sarsfield',
    997:  'River Plate',
    998:  'Boca Juniors',
    8:    'Racing Club',
    50:   'Independiente',
    1026: 'San Lorenzo',
    16503:'Lanus',
    3380: 'Estudiantes',
    1038: 'Huracan',
    16497:'Banfield',
}


def parse_valor(text):
    """Convierte '2,50 mill. EUR' o '500 mil EUR' a float en EUR."""
    if not text:
        return 0
    text = text.replace('\xa0', ' ').strip()
    match = re.search(r'([\d,.]+)\s*(mill\.|mil|M|k)?', text, re.IGNORECASE)
    if not match:
        return 0
    num = float(match.group(1).replace(',', '.'))
    unit = (match.group(2) or '').lower()
    if 'mill' in unit or unit == 'm':
        return int(num * 1_000_000)
    elif 'mil' in unit or unit == 'k':
        return int(num * 1_000)
    return int(num)


def scrape(club_id):
    url = f'https://www.transfermarkt.es/verein/kader/verein/{club_id}'
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, 'html.parser')
    rows = soup.select('table.items tbody tr.odd, table.items tbody tr.even')

    jugadores = []
    seen = set()

    for row in rows:
        nombre_tag = row.select_one('td.hauptlink a')
        if not nombre_tag:
            continue
        nombre = nombre_tag.get_text(strip=True)
        if nombre in seen:
            continue
        seen.add(nombre)

        posicion_tag = row.select_one('td.posrela table tr:nth-child(2) td')
        posicion = posicion_tag.get_text(strip=True) if posicion_tag else ''

        edad_cells = row.find_all('td', class_='zentriert')
        edad = ''
        if len(edad_cells) >= 2:
            edad = edad_cells[1].get_text(strip=True)

        valor_tag = row.select_one('td.rechts.hauptlink')
        valor_text = valor_tag.get_text(strip=True) if valor_tag else ''
        valor_eur = parse_valor(valor_text)

        celdas_centro = row.find_all('td', class_='zentriert')
        contrato = ''
        if len(celdas_centro) >= 4:
            contrato = celdas_centro[-1].get_text(strip=True)

        jugadores.append({
            'nombre': nombre,
            'posicion': posicion,
            'edad': edad,
            'valor_eur': valor_eur,
            'contrato_hasta': contrato,
        })

    valor_total = sum(j['valor_eur'] for j in jugadores)
    club_nombre = CLUBS.get(club_id, f'Club {club_id}')

    return {
        'club': club_nombre,
        'club_id': club_id,
        'fecha_extraccion': str(date.today()),
        'fuente': f'https://www.transfermarkt.es/verein/kader/verein/{club_id}',
        'valor_total_eur': valor_total,
        'jugadores': jugadores,
    }


def main():
    parser = argparse.ArgumentParser(description='Scraper Transfermarkt — plantel argentino')
    parser.add_argument('--club-id', type=int, required=True, help='ID del club en Transfermarkt')
    parser.add_argument('--output', type=str, default=None, help='Archivo JSON de salida (stdout si no se especifica)')
    args = parser.parse_args()

    data = scrape(args.club_id)

    output_json = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f'OK — {len(data["jugadores"])} jugadores, EUR {data["valor_total_eur"]:,} total → {args.output}')
    else:
        print(output_json)


if __name__ == '__main__':
    main()
