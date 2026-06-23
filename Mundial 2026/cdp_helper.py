"""
cdp_helper.py — CDP helper via pychrome para Chrome 149+
(reemplaza el connect_over_cdp de Playwright que falla con Chrome 149)
"""
import json, time, requests
import pychrome


_TAB_ID   = None
_TAB      = None
_XCAPTCHA = ""
_XREQUESTED = "441959"


def _make_tab():
    """Crea una tab nueva y navega a SofaScore capturando el x-captcha."""
    global _TAB_ID, _TAB, _XCAPTCHA, _XREQUESTED

    # Crear tab en blanco
    new = requests.put("http://localhost:9222/json/new?about:blank").json()
    _TAB_ID = new["id"]
    _TAB = pychrome.Tab(**new)
    _TAB.start()

    # Inyectar interceptor fetch ANTES de navegar
    _TAB.call_method("Page.enable", timeout=5)
    _TAB.call_method("Runtime.evaluate",
        expression="""
        window.__captcha__ = '';
        window.__xrw__     = '441959';
        const _origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (opts && opts.headers) {
                const h = opts.headers;
                if (h['x-captcha'])        window.__captcha__ = h['x-captcha'];
                if (h['x-requested-with']) window.__xrw__     = h['x-requested-with'];
            }
            return _origFetch.apply(this, arguments);
        };
        """,
        timeout=5
    )

    # Navegar a SofaScore
    _TAB.call_method("Page.navigate",
        url="https://www.sofascore.com/football/player/erling-haaland/839956",
        timeout=15
    )
    time.sleep(5)

    # Scroll para triggear más API calls
    _TAB.call_method("Runtime.evaluate", expression="window.scrollTo(0, 500)", timeout=5)
    time.sleep(2)

    # Leer token capturado
    r = _TAB.call_method("Runtime.evaluate",
        expression="JSON.stringify({c: window.__captcha__, x: window.__xrw__})",
        returnByValue=True, timeout=5
    )
    val = r.get("result", {}).get("value", "{}")
    d   = json.loads(val)
    _XCAPTCHA   = d.get("c", "")
    _XREQUESTED = d.get("x", "441959") or "441959"
    print(f"  x-captcha: {'OK ('+_XCAPTCHA[:12]+')' if _XCAPTCHA else 'MISSING'} | xrw={_XREQUESTED}")
    return bool(_XCAPTCHA)


def init():
    """Inicializa la tab CDP. Retorna True si capturó x-captcha."""
    ok = _make_tab()
    if not ok:
        # Segundo intento: esperar más y hacer scroll adicional
        time.sleep(3)
        _TAB.call_method("Runtime.evaluate", expression="window.scrollTo(0, 1000)", timeout=5)
        time.sleep(2)
        r = _TAB.call_method("Runtime.evaluate",
            expression="JSON.stringify({c: window.__captcha__, x: window.__xrw__})",
            returnByValue=True, timeout=5
        )
        val = r.get("result", {}).get("value", "{}")
        d = json.loads(val)
        global _XCAPTCHA, _XREQUESTED
        _XCAPTCHA   = d.get("c", "")
        _XREQUESTED = d.get("x", "441959") or "441959"
        print(f"  2do intento — x-captcha: {'OK' if _XCAPTCHA else 'MISSING'}")
    return bool(_XCAPTCHA)


def close():
    """Cierra la tab CDP."""
    global _TAB, _TAB_ID
    if _TAB:
        try:
            _TAB.stop()
        except Exception:
            pass
    if _TAB_ID:
        try:
            requests.get(f"http://localhost:9222/json/close/{_TAB_ID}", timeout=3)
        except Exception:
            pass
    _TAB = _TAB_ID = None


def api_call(url, retries=3):
    """
    Hace un fetch a la SofaScore API desde dentro de la tab CDP.
    Retorna el dict JSON o None si falla.
    """
    global _XCAPTCHA, _XREQUESTED

    cap = _XCAPTCHA.replace("'", "\\'")
    xrw = _XREQUESTED.replace("'", "\\'")
    js  = f"""
    (async () => {{
        try {{
            const r = await fetch('{url}', {{
                credentials: 'include',
                headers: {{
                    'x-captcha':        '{cap}',
                    'x-requested-with': '{xrw}',
                    'Accept':           'application/json',
                }}
            }});
            // Actualizar token si la página lo renovó
            if (window.__captcha__) window.__captcha__ = window.__captcha__;
            return await r.text();
        }} catch(e) {{ return JSON.stringify({{fetch_error: e.toString()}}); }}
    }})()
    """

    for attempt in range(retries):
        try:
            result = _TAB.call_method("Runtime.evaluate",
                expression=js,
                awaitPromise=True,
                returnByValue=True,
                timeout=20
            )
            raw = result.get("result", {}).get("value", "")
            if not raw:
                time.sleep(2)
                continue
            data = json.loads(raw)
            if "fetch_error" in data:
                time.sleep(2)
                continue
            if "error" in data and data.get("error", {}).get("code") in (403, 429):
                # Renovar token
                r2 = _TAB.call_method("Runtime.evaluate",
                    expression="JSON.stringify({c: window.__captcha__, x: window.__xrw__})",
                    returnByValue=True, timeout=5
                )
                d2 = json.loads(r2.get("result", {}).get("value", "{}"))
                _XCAPTCHA   = d2.get("c", _XCAPTCHA)
                _XREQUESTED = d2.get("x", _XREQUESTED)
                time.sleep(3 + attempt * 2)
                continue
            return data
        except Exception as e:
            print(f"    api_call warn ({attempt+1}/{retries}): {e}")
            time.sleep(3)
    return None
