"""
scrape_footystats_xg.py — Extrae xG por equipo de FootyStats para Liga de Primera Chile 2026.

Uso:
    python scrape_footystats_xg.py --output footystats_xg.json
"""
import sys, io, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

URL = "https://footystats.org/chile/primera-division/xg"

def scrape(output_path=None):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        print(f"Navegando a {URL}...")
        page.goto(URL, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(6000)  # esperar JS dinámico

        # Intentar hacer scroll para cargar todos los datos
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

        # Extraer tabla: buscar todos los elementos con datos de equipo
        # FootyStats usa tablas o listas con clases específicas
        html = page.content()

        # Intentar extraer via JS directo del DOM
        teams = page.evaluate("""
        () => {
            const result = [];
            // Selector para filas de tabla de equipos en FootyStats
            const selectors = [
                'table tbody tr',
                '.league-table-body tr',
                '[class*="team-row"]',
                'tr[data-team-id]',
            ];
            let rows = [];
            for (const sel of selectors) {
                rows = document.querySelectorAll(sel);
                if (rows.length > 5) break;
            }

            rows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                if (cells.length < 3) return;

                // Buscar nombre del equipo
                const nameEl = row.querySelector('a[href*="/clubs/"], td.team-name, td:first-child a, .team-name-cell');
                const name = nameEl ? nameEl.textContent.trim() : cells[0].textContent.trim();
                if (!name || name.length < 3) return;

                // Extraer todos los valores de celdas
                const vals = cells.map(c => c.textContent.trim());
                result.push({ name, cells: vals });
            });
            return result;
        }
        """)

        # También intentar extraer xG específicamente buscando en texto
        xg_data = page.evaluate("""
        () => {
            // FootyStats muestra datos con atributos data-* o en spans específicos
            const result = [];
            const rows = document.querySelectorAll('tr');
            rows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                if (cells.length < 4) return;
                const text = row.textContent;
                // Buscar filas con valores decimales que parecen xG (entre 0.5 y 3.0)
                const nums = text.match(/\d+\.\d+/g);
                if (!nums || nums.length < 2) return;
                const nameEl = row.querySelector('a');
                const name = nameEl ? nameEl.textContent.trim() : cells[0].textContent.trim();
                if (name) result.push({name, raw: text.trim().substring(0,200), nums});
            });
            return result;
        }
        """)

        browser.close()

    result = {"raw_rows": teams, "xg_rows": xg_data, "_html_length": len(html)}

    # Guardar HTML para inspección si los datos no están claros
    with open("footystats_debug.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML guardado en footystats_debug.html ({len(html)} chars)")

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Guardado en {output_path}")

    # Mostrar resumen
    print(f"\nFilas encontradas (DOM rows): {len(teams)}")
    for t in teams[:8]:
        print(f"  {t['name'][:30]:30s} | {' | '.join(t['cells'][:6])}")
    print(f"\nFilas con números decimales: {len(xg_data)}")
    for t in xg_data[:8]:
        print(f"  {t['name'][:30]:30s} nums={t['nums'][:6]}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="footystats_xg.json")
    args = parser.parse_args()
    scrape(args.output)
