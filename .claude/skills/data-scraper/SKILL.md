---
name: data-scraper
description: Scrape market values, financial data, and socios data that can't be fetched via standard WebFetch. Use this skill when the dashboard builder hits 403s or binary PDFs. Covers Transfermarkt (market values + contract dates), club balance PDFs (full financial statements via pdfplumber), and club official sites (socios, cuotas). TRIGGER when: Transfermarkt returns 403, a balance PDF is needed, or socios data is missing. Dependencies: requests, beautifulsoup4, pdfplumber==0.10.4 — install before running.
---

# Data Scraper — Argentine Football Clubs

Herramienta de scraping para obtener datos que WebFetch no puede acceder directamente.
Provee scripts testeados y listos para usar.

## Lo que funciona (confirmado en tests)

| Fuente | Método | Qué obtiene |
|---|---|---|
| **Transfermarkt** | requests + BS4 con browser headers | Valor de mercado EUR, posición, edad, fecha fin contrato |
| **Balance PDF (velez.com.ar)** | requests download + pdfplumber 0.10.4 | Estado de situación patrimonial, recursos y gastos, resultado |
| **Sitio oficial del club** | requests + BS4 | Solo si el sitio renderiza cuotas en HTML estático (no Vélez) |

## Lo que NO funciona

| Fuente | Por qué |
|---|---|
| SofaScore API | 403 incluso con browser headers |
| Transfermarkt vía WebFetch | Bloqueado por el crawler de Anthropic |
| PDFs vía WebFetch | Devuelve binario no procesable |
| velezsarsfield.com.ar/socios/valores | Cuotas cargadas por JavaScript — requests+BS4 devuelve HTML vacío. Necesitaría Playwright. Usar prensa (Doble Amarilla, Infobae) para obtener cuotas vigentes. |

## Dependencias

```bash
pip install requests beautifulsoup4 "pdfplumber==0.10.4"
```

Nota: pdfplumber 0.11+ tiene un bug con `LTRect.original_path` en PDFs de clubes argentinos. Usar exactamente 0.10.4.

## Workflow

### Paso 1 — Verificar dependencias
```bash
python -c "import requests, bs4, pdfplumber; print('OK')"
```
Si falla, correr el pip install de arriba.

### Paso 2 — Elegir el script según lo que se necesita

- Valores de mercado del plantel → `scripts/transfermarkt.py`
- Balance completo desde PDF → `scripts/pdf_balance.py`
- Cuotas y socios del sitio oficial → `scripts/socios_oficial.py`

### Paso 3 — Correr el script con el club y guardar output

Cada script imprime JSON o CSV a stdout. Redirigir a un archivo o leer el output para poblar los Excel del dashboard.

---

## Script: transfermarkt.py

Obtiene el plantel completo de Transfermarkt con valores de mercado, posición, edad y fecha fin de contrato.

**IDs de clubes argentinos en Transfermarkt:**
- Vélez Sársfield: `1029`
- River Plate: `997`
- Boca Juniors: `998`
- Racing Club: `1444`
- Independiente: `50`
- San Lorenzo: `1026`
- Lanús: `16503`
- Estudiantes: `3380`
- Huracán: `1038`
- Banfield: `16497`

**Uso:**
```bash
python scripts/transfermarkt.py --club-id 1029 --output plantel_tm.json
```

---

## Script: pdf_balance.py

Descarga el PDF del balance anual desde el sitio oficial del club y extrae con pdfplumber:
- Estado de situación patrimonial (activo, pasivo, patrimonio neto)
- Estado de recursos y gastos (recursos ordinarios, gastos, resultado)
- Datos comparativos del ejercicio anterior

**URLs de balance de Vélez:**
- Ej. 115 (2024-25): `https://ftp.velezsarsfield.com.ar/pdf/memoria-balance-general-2025.pdf`
- Ej. 114 (2023-24): `https://velez.com.ar/pdf/2024-balance-general.pdf`
- Ej. 113 (2022-23): `https://velez.com.ar/pdf/2023-balance-general.pdf`
- Ej. 112 (2021-22): `https://velez.com.ar/pdf/memoria-balance-general-2021-2022.pdf`

**Uso:**
```bash
python scripts/pdf_balance.py --url "https://velez.com.ar/pdf/2024-balance-general.pdf" --output balance_ej114.json
```

---

## Script: socios_oficial.py

Scrapea el sitio oficial del club para obtener cuotas sociales actuales e historial de anuncios.

**Uso:**
```bash
python scripts/socios_oficial.py --club velez --output socios.json
```

---

## Datos estructurados que devuelve cada script

### transfermarkt.py → JSON
```json
{
  "club": "Vélez Sársfield",
  "club_id": 1029,
  "fecha_extraccion": "2026-04-19",
  "valor_total_eur": 32230000,
  "jugadores": [
    {
      "nombre": "Tobías Andrada",
      "posicion": "Mediocentro",
      "edad": 19,
      "valor_eur": 3000000,
      "contrato_hasta": "31/12/2029"
    }
  ]
}
```

### pdf_balance.py → JSON
```json
{
  "club": "Vélez Sársfield",
  "ejercicio": 114,
  "periodo": "2023-07-01 / 2024-06-30",
  "fecha_extraccion": "2026-04-19",
  "fuente_url": "https://velez.com.ar/pdf/2024-balance-general.pdf",
  "situacion_patrimonial": {
    "total_activo": 67571780434,
    "activo_corriente": 15961518431,
    "activo_no_corriente": 51610262003,
    "total_pasivo": 24945959441,
    "patrimonio_neto": 42625820993
  },
  "recursos_gastos": {
    "recursos_ordinarios_total": 46598890489,
    "gastos_ordinarios_total": 63116161701,
    "resultados_financieros": 15404132114,
    "resultado_ejercicio": -1113139098
  }
}
```
