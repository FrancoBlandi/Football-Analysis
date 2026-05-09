#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_bpr_html.py — Lee el HTML de /estadisticas/bpr y busca datos embebidos.
"""
import json, sys, io, re, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CDP_URL = "http://127.0.0.1:9222"
FM_URL  = "https://fantasymanager.ar"
OUT     = Path(__file__).parent / "bpr_html_dump.json"


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright")

    import urllib.request
    try:
        urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
    except Exception:
        sys.exit("Chrome no está con --remote-debugging-port=9222")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx  = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        results = {}

        for path in ["/estadisticas/bpr", "/estadisticas/figura"]:
            print(f"\nCargando {path}...")
            page.goto(f"{FM_URL}{path}", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Texto visible de la página
            body_text = page.evaluate("document.body.innerText")
            print(f"  Primeros 800 chars del texto visible:")
            print(f"  {body_text[:800]}")

            # Buscar JSON en scripts
            scripts = page.evaluate("""
                () => Array.from(document.querySelectorAll('script'))
                          .map(s => s.innerText || s.textContent)
                          .filter(t => t.length > 50)
            """)
            print(f"\n  Scripts encontrados: {len(scripts)}")
            for i, s in enumerate(scripts):
                if any(k in s.lower() for k in ["bpr", "mvp", "figura", "bonus", "player", "round"]):
                    print(f"  Script {i} (relevante, {len(s)} chars): {s[:400]}")

            # Buscar __NEXT_DATA__ o similar (Next.js SSR)
            next_data = page.evaluate("""
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? el.textContent : null;
                }
            """)
            if next_data:
                print(f"\n  __NEXT_DATA__ encontrado ({len(next_data)} chars)")
                try:
                    nd = json.loads(next_data)
                    print(f"  Keys: {list(nd.keys())}")
                    # Buscar datos de BPR en props
                    nd_str = json.dumps(nd)
                    if any(k in nd_str.lower() for k in ["bpr", "mvp", "figura"]):
                        print("  Contiene BPR data!")
                        # Buscar el subnodo relevante
                        props = nd.get("props", {}).get("pageProps", {})
                        print(f"  pageProps keys: {list(props.keys())}")
                        for k, v in props.items():
                            print(f"    {k}: {str(v)[:200]}")
                    results[path] = nd
                except Exception as e:
                    print(f"  Error parseando __NEXT_DATA__: {e}")

            # Screenshot
            slug = path.replace("/", "_")
            page.screenshot(path=str(Path(__file__).parent / f"bpr_html{slug}.png"),
                           full_page=True)
            print(f"  Screenshot guardado")

        page.close()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nDump guardado en {OUT}")


if __name__ == "__main__":
    main()
