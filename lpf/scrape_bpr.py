#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_bpr.py — BPR (Bonus por Rendimiento) de Fantasy Manager AR

Flujo:
  1. Abrís Chrome manualmente con el flag de debug (ver instrucciones abajo)
  2. Te logueás en fantasymanager.ar con tu cuenta Google
  3. Corrés este script — se conecta al Chrome que ya está abierto

Cómo abrir Chrome con debug habilitado (pegar en CMD):
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --no-first-run

Uso:
    python lpf/scrape_bpr.py
    python lpf/scrape_bpr.py --explore   # solo exploración, no guarda datos
"""

import json, sys, io, argparse, subprocess, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = "https://fantasymanager.ar"
OUT_PATH  = Path(__file__).parent / "bpr_data.json"
LOG_PATH  = Path(__file__).parent / "bpr_explore_log.json"
CDP_URL   = "http://127.0.0.1:9222"


def explore(page, api_calls):
    """Navega por /estadisticas capturando todas las llamadas de red."""
    print("\nNavegando a /estadisticas...")
    page.goto(f"{BASE_URL}/estadisticas", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    page.screenshot(path=str(Path(__file__).parent / "bpr_estadisticas.png"))
    print(f"  Screenshot guardado — título: {page.title()}")

    # Scroll para cargar lazy content
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    # Loguear elementos clickeables
    tabs = page.query_selector_all('button, a, [role="tab"]')
    tab_texts = [t.inner_text().strip() for t in tabs[:30] if t.inner_text().strip()]
    print(f"  Clickeables: {tab_texts[:20]}")

    # Buscar y clickear sección "Figura"
    figura_els = page.query_selector_all('*:has-text("Figura"), *:has-text("BPR"), *:has-text("Bonus")')
    for el in figura_els[:5]:
        try:
            txt = el.inner_text().strip()[:100]
            if txt:
                print(f"  Figura/BPR encontrado: {txt!r}")
                el.click()
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  click fallido: {e}")

    page.wait_for_timeout(2000)

    # Sub-rutas conocidas
    for path in ["/estadisticas/figura", "/estadisticas/bpr", "/estadisticas/bonus",
                 "/estadisticas/jugadores", "/estadisticas/rendimiento"]:
        try:
            page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded", timeout=8000)
            page.wait_for_timeout(1500)
            cur = page.url
            if "login" not in cur and cur not in (f"{BASE_URL}/", BASE_URL):
                print(f"  Página válida: {cur}")
                page.wait_for_timeout(2500)
                slug = path.split("/")[-1]
                page.screenshot(path=str(Path(__file__).parent / f"bpr_{slug}.png"))
        except Exception as e:
            print(f"  {path}: {e}")

    # Volver a base y esperar
    page.goto(f"{BASE_URL}/estadisticas", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    print(f"\n  Total llamadas API capturadas: {len(api_calls)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--explore", action="store_true")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta: pip install playwright && playwright install chromium")

    print("=" * 60)
    print("Fantasy Manager AR — Scraper BPR (via CDP)")
    print("=" * 60)

    CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    # Matar todas las instancias de Chrome existentes
    print("\nCerrando Chrome existente...")
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
    time.sleep(2)

    # Usar perfil temporal para evitar locks y diálogos de crash recovery
    import tempfile
    tmp_profile = tempfile.mkdtemp(prefix="chrome_bpr_")

    # Lanzar Chrome con debug port
    print(f"Lanzando Chrome con debug port 9222 (perfil temporal: {tmp_profile})...")
    subprocess.Popen([
        CHROME_EXE,
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-crash-upload",
        f"--user-data-dir={tmp_profile}",
        "https://fantasymanager.ar/login",
    ])

    # Esperar a que el puerto esté disponible
    import urllib.request
    print("Esperando a que Chrome levante el puerto de debug", end="", flush=True)
    for _ in range(60):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
            print(" OK")
            break
        except Exception:
            print(".", end="", flush=True)
    else:
        print("\nERROR: Chrome no levantó el puerto de debug en 60s.")
        sys.exit(1)

    print("\nChrome abierto en https://fantasymanager.ar")
    input(">>> Loguéate si es necesario, luego presioná Enter para continuar...")

    api_calls = []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\nERROR: No se pudo conectar al Chrome en {CDP_URL}")
            print(f"  {e}")
            print("\nAsegurate de haber abierto Chrome con --remote-debugging-port=9222")
            sys.exit(1)

        print(f"  Conectado a Chrome. Contextos: {len(browser.contexts)}")

        # Usar el contexto existente (con la sesión de Fantasy Manager)
        if browser.contexts:
            ctx = browser.contexts[0]
        else:
            ctx = browser.new_context()

        page = ctx.new_page()

        # Interceptar llamadas de red
        KEYWORDS = ["api", "stats", "bpr", "figura", "bonus", "player", "jugador",
                    "rendimiento", "estadistica", "ranking", "points", "puntos",
                    "performance", "score", "match"]

        def on_response(response):
            url = response.url
            if any(x in url.lower() for x in KEYWORDS):
                try:
                    body = response.json()
                    api_calls.append({"url": url, "status": response.status, "body": body})
                    print(f"  [API] {response.status} {url[:120]}")
                except Exception:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        api_calls.append({"url": url, "status": response.status, "body": None})
                        print(f"  [API-noparse] {url[:120]}")

        page.on("response", on_response)

        # Verificar sesión
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        print(f"  URL: {page.url} | Título: {page.title()}")

        if "login" in page.url:
            print("\nSesión no activa. Loguéate en la ventana de Chrome y presioná Enter.")
            input(">>> Enter cuando estés logueado...")

        explore(page, api_calls)

        # No cerramos el browser (es el Chrome del usuario)
        page.close()

    # ── Guardar log ──
    log = []
    for c in api_calls:
        b = c["body"]
        if isinstance(b, (list, dict)):
            s = json.dumps(b)
            b_str = s[:2000] + ("..." if len(s) > 2000 else "")
        else:
            b_str = str(b)
        log.append({"url": c["url"], "status": c["status"], "body_preview": b_str})

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\nLog guardado en {LOG_PATH}")
    print(f"Total llamadas API: {len(api_calls)}")

    if api_calls:
        print("\nURLs capturadas:")
        for c in api_calls:
            print(f"  {c['status']} {c['url']}")

    if not api_calls:
        print("\nNo se capturaron llamadas. Revisar bpr_estadisticas.png.")
        return

    # ── Filtrar candidatos BPR ──
    bpr_candidates = [
        c for c in api_calls if c["body"] and
        any(k in json.dumps(c["body"]).lower()
            for k in ["figura", "bpr", "bonus", "jugador", "rating", "performance"])
    ]

    if bpr_candidates:
        print(f"\nEndpoints con datos BPR: {len(bpr_candidates)}")
        for c in bpr_candidates:
            print(f"\n  URL: {c['url']}")
            print(f"  Preview: {json.dumps(c['body'])[:600]}")

        if not args.explore:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "endpoints": [c["url"] for c in bpr_candidates],
                    "data": bpr_candidates,
                }, f, ensure_ascii=False, indent=2)
            print(f"\nDatos guardados en {OUT_PATH}")
    else:
        print("\nNo se encontraron endpoints con datos de BPR/Figura.")
        print("Revisar bpr_explore_log.json para identificar endpoints manualmente.")


if __name__ == "__main__":
    main()
