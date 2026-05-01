"""
pdf_balance.py — Extrae estado patrimonial y recursos/gastos de PDFs de balance de clubes argentinos

Uso:
    python pdf_balance.py --url "https://velez.com.ar/pdf/2024-balance-general.pdf" --output balance.json

Dependencias:
    pip install requests "pdfplumber==0.10.4" "pdfminer.six==20221105"

IMPORTANTE: pdfplumber 0.11+ tiene un bug con LTRect.original_path en PDFs de clubes argentinos.
Usar EXACTAMENTE pdfplumber==0.10.4.
"""

import argparse
import io
import json
import re
import sys
from datetime import date

import requests

try:
    import pdfplumber
except ImportError:
    print('ERROR: pdfplumber no instalado. Correr: pip install "pdfplumber==0.10.4"')
    sys.exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/pdf,*/*;q=0.8',
    'Referer': 'https://www.google.com/',
}


def limpiar_numero(text):
    """Convierte '( 1.113.139.098)' o '42.625.820.993' a int."""
    if not text:
        return None
    negativo = '(' in text
    limpio = re.sub(r'[^\d]', '', text)
    if not limpio:
        return None
    valor = int(limpio)
    return -valor if negativo else valor


def buscar_linea(lineas, patron):
    """Busca la primera línea que contiene el patrón (case insensitive) y devuelve el número al final."""
    pat = re.compile(patron, re.IGNORECASE)
    for linea in lineas:
        if pat.search(linea):
            nums = re.findall(r'[\(\d][\d.,\s]*[\d\)]', linea)
            if nums:
                return limpiar_numero(nums[-1])
    return None


def extraer_pagina(pdf, idx):
    if idx >= len(pdf.pages):
        return ''
    return pdf.pages[idx].extract_text() or ''


def parsear_situacion_patrimonial(texto_activo, texto_pasivo):
    lineas_activo = texto_activo.splitlines()
    lineas_pasivo = texto_pasivo.splitlines()
    todas = lineas_activo + lineas_pasivo

    return {
        'total_activo': buscar_linea(lineas_activo, r'total.*activo'),
        'activo_corriente': buscar_linea(lineas_activo, r'activo.*corriente'),
        'activo_no_corriente': buscar_linea(lineas_activo, r'activo.*no.*corriente'),
        'total_pasivo': buscar_linea(lineas_pasivo, r'total.*pasivo'),
        'pasivo_corriente': buscar_linea(lineas_pasivo, r'pasivo.*corriente'),
        'pasivo_no_corriente': buscar_linea(lineas_pasivo, r'pasivo.*no.*corriente'),
        'patrimonio_neto': buscar_linea(todas, r'patrimonio.*neto'),
    }


def parsear_recursos_gastos(texto):
    lineas = texto.splitlines()
    return {
        'recursos_ordinarios_total': buscar_linea(lineas, r'total.*recursos.*ordinarios|recursos.*ordinarios.*total'),
        'gastos_ordinarios_total': buscar_linea(lineas, r'total.*gastos.*ordinarios|gastos.*ordinarios.*total'),
        'resultados_financieros': buscar_linea(lineas, r'resultados.*financieros|resultado.*financiero'),
        'resultado_ejercicio': buscar_linea(lineas, r'resultado.*del.*ejercicio|resultado.*ejercicio'),
    }


def extraer_balance(url):
    print(f'Descargando PDF: {url}')
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        n = len(pdf.pages)
        print(f'PDF cargado: {n} paginas')

        # Vélez: páginas 6, 7 (activo/pasivo) y 8 (recursos/gastos)
        # Buscar las páginas correctas por contenido
        idx_activo = None
        idx_pasivo = None
        idx_rg = None

        for i in range(n):
            texto = extraer_pagina(pdf, i).lower()
            if 'activo corriente' in texto and idx_activo is None:
                idx_activo = i
            if 'pasivo corriente' in texto and idx_pasivo is None:
                idx_pasivo = i
            if 'recursos ordinarios' in texto and idx_rg is None:
                idx_rg = i

        print(f'Paginas detectadas — Activo: {idx_activo}, Pasivo: {idx_pasivo}, RecursosGastos: {idx_rg}')

        texto_activo = extraer_pagina(pdf, idx_activo) if idx_activo is not None else ''
        texto_pasivo = extraer_pagina(pdf, idx_pasivo) if idx_pasivo is not None else ''
        texto_rg = extraer_pagina(pdf, idx_rg) if idx_rg is not None else ''

    situacion = parsear_situacion_patrimonial(texto_activo, texto_pasivo)
    recursos = parsear_recursos_gastos(texto_rg)

    return {
        'fecha_extraccion': str(date.today()),
        'fuente_url': url,
        'situacion_patrimonial': situacion,
        'recursos_gastos': recursos,
        '_debug': {
            'pagina_activo': idx_activo,
            'pagina_pasivo': idx_pasivo,
            'pagina_recursos_gastos': idx_rg,
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Extractor de balance PDF — clubes argentinos')
    parser.add_argument('--url', required=True, help='URL del PDF de balance')
    parser.add_argument('--output', default=None, help='Archivo JSON de salida (stdout si no se especifica)')
    args = parser.parse_args()

    data = extraer_balance(args.url)

    output_json = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f'OK — balance extraido -> {args.output}')
    else:
        print(output_json)


if __name__ == '__main__':
    main()
