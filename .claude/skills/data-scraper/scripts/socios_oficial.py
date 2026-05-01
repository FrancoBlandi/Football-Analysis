"""
socios_oficial.py — Scraper de cuotas sociales desde sitios oficiales de clubes argentinos

Uso:
    python socios_oficial.py --club velez --output socios.json

Clubes soportados: velez, racing, lanus, san-lorenzo, independiente, banfield, huracan

Dependencias:
    pip install requests beautifulsoup4
"""

import argparse
import io
import json
import re
import sys
from datetime import date

# Windows cp1252 fix
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

CLUBS_CONFIG = {
    'velez': {
        'nombre': 'Velez Sarsfield',
        'urls': [
            'https://www.velezsarsfield.com.ar/socios',
            'https://www.velezsarsfield.com.ar/institucional/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'racing': {
        'nombre': 'Racing Club',
        'urls': [
            'https://www.racingclub.com.ar/socios',
            'https://racingclub.com.ar/institucional/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'lanus': {
        'nombre': 'Club Atletico Lanus',
        'urls': [
            'https://www.clubatlantilanus.com.ar/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'san-lorenzo': {
        'nombre': 'San Lorenzo de Almagro',
        'urls': [
            'https://www.sanlorenzo.com.ar/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'independiente': {
        'nombre': 'Club Atletico Independiente',
        'urls': [
            'https://www.independiente.com.ar/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'banfield': {
        'nombre': 'Club Atletico Banfield',
        'urls': [
            'https://www.clubatleticobanfield.com.ar/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
    'huracan': {
        'nombre': 'Club Atletico Huracan',
        'urls': [
            'https://www.cahuracan.com.ar/socios',
        ],
        'patron_cuota': r'cuota.*?(\$\s*[\d.,]+)',
        'patron_categoria': r'(activo|adherente|joven|familiar|infantil)',
    },
}


def limpiar_monto(text):
    """Convierte '$38.000' o '$ 38,000' a int."""
    limpio = re.sub(r'[^\d]', '', text)
    return int(limpio) if limpio else None


def extraer_cuotas_de_texto(texto, patron_categoria):
    """Busca patrones de cuota en texto libre."""
    cuotas = []
    lineas = texto.splitlines()
    for linea in lineas:
        if re.search(patron_categoria, linea, re.IGNORECASE):
            match_monto = re.search(r'\$\s*([\d.,]+)', linea)
            if match_monto:
                categoria = re.search(patron_categoria, linea, re.IGNORECASE)
                cuotas.append({
                    'categoria': categoria.group(1).capitalize() if categoria else 'General',
                    'cuota_mensual_ars': limpiar_monto(match_monto.group(0)),
                    'texto_original': linea.strip(),
                })
    return cuotas


def scrape_club(config):
    resultados = {
        'cuotas': [],
        'url_exitosa': None,
        'errores': [],
    }

    for url in config['urls']:
        try:
            print(f'Probando: {url}')
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 404:
                resultados['errores'].append(f'{url} → 404')
                continue
            r.raise_for_status()

            soup = BeautifulSoup(r.text, 'html.parser')
            texto = soup.get_text(separator='\n')

            cuotas = extraer_cuotas_de_texto(texto, config['patron_categoria'])

            if cuotas:
                resultados['cuotas'] = cuotas
                resultados['url_exitosa'] = url
                print(f'OK — {len(cuotas)} categorias encontradas en {url}')
                break
            else:
                # Guardar para debug aunque no se encontraron cuotas
                resultados['errores'].append(f'{url} → sin cuotas detectadas (status {r.status_code})')
                resultados['url_exitosa'] = url
                resultados['_html_snippet'] = texto[:2000]

        except requests.RequestException as e:
            resultados['errores'].append(f'{url} → {str(e)}')

    return resultados


def main():
    parser = argparse.ArgumentParser(description='Scraper de cuotas sociales — clubes argentinos')
    parser.add_argument('--club', required=True, choices=list(CLUBS_CONFIG.keys()), help='Slug del club')
    parser.add_argument('--output', default=None, help='Archivo JSON de salida (stdout si no se especifica)')
    args = parser.parse_args()

    config = CLUBS_CONFIG[args.club]
    print(f'Scrapeando socios de {config["nombre"]}...')

    scrape_result = scrape_club(config)

    data = {
        'club': config['nombre'],
        'fecha_extraccion': str(date.today()),
        'fuente_url': scrape_result['url_exitosa'],
        'cuotas': scrape_result['cuotas'],
        '_errores': scrape_result['errores'],
    }

    if '_html_snippet' in scrape_result:
        data['_html_snippet_debug'] = scrape_result['_html_snippet']

    output_json = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        n = len(data['cuotas'])
        if n > 0:
            print(f'OK — {n} categorias de cuotas -> {args.output}')
        else:
            print(f'ATENCION — no se encontraron cuotas. Revisar _html_snippet_debug en el output para ajustar patrones.')
    else:
        print(output_json)


if __name__ == '__main__':
    main()
