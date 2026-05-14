"""
cruzar_tm_sofascore.py — Cruza goleadores de Transfermarkt vs SofaScore incidents
para todos los partidos del Apertura 2026, buscando atribuciones erróneas.

TM:        goleadores por partido (sin minutos, con flag autogol/penal)
SofaScore: incidents filtrados (sin autogoles), vía Playwright

Matching de nombres: normalización + coincidencia por apellido principal.
"""

import sys, io, json, re, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-UY,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TM_BASE = "https://www.transfermarkt.com.ar"


# ─── Normalización de nombres ─────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Lowercase, sin acentos, solo letras y espacios."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^a-z ]", "", name.lower())
    return " ".join(name.split())

def apellido_principal(nombre_norm: str) -> str:
    """Último token como apellido principal (heurística simple)."""
    parts = nombre_norm.split()
    return parts[-1] if parts else nombre_norm

def nombres_match(n1: str, n2: str) -> bool:
    """True si los nombres normalizados comparten al menos el apellido principal."""
    n1n, n2n = normalize(n1), normalize(n2)
    if n1n == n2n:
        return True
    ap1, ap2 = apellido_principal(n1n), apellido_principal(n2n)
    if ap1 == ap2 and len(ap1) > 3:
        return True
    # También chequeamos si uno está contenido en el otro (nombre abreviado)
    parts1, parts2 = set(n1n.split()), set(n2n.split())
    common = parts1 & parts2
    if common and max(len(w) for w in common) > 3:
        return True
    return False


# ─── Scraping Transfermarkt ───────────────────────────────────────────────────

def get_tm_jornada_match_ids(jornada: int) -> list:
    """Retorna lista de (match_id, score_home, score_away) para una jornada."""
    url = (f"{TM_BASE}/primera-division/spieltag/wettbewerb/URU1"
           f"/plus/0?saison_id=2025&spieltag={jornada}")
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    seen, matches = set(), []
    for a in soup.find_all("a", href=re.compile(r"/spielbericht/index/spielbericht/\d+")):
        mid = re.search(r"/spielbericht/(\d+)", a["href"]).group(1)
        if mid in seen:
            continue
        seen.add(mid)
        score_text = a.get_text(strip=True)  # e.g. "3:1"
        m = re.match(r"(\d+):(\d+)", score_text)
        sh, sa = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        matches.append((mid, sh, sa))
    return matches


def get_tm_goalscorers(match_id: str) -> dict:
    """
    Retorna {
        "home_name": str,
        "away_name": str,
        "home": [{"nombre": str, "tipo": "regular"|"penalty"|"owngoal"}],
        "away": [...],
    }
    sb-aktion-heim = gol que beneficia al LOCAL (incluyendo autogol del visitante)
    sb-aktion-gast = gol que beneficia al VISITANTE
    """
    url = f"{TM_BASE}/spielbericht/index/spielbericht/{match_id}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    result = {"home": [], "away": [], "home_name": "", "away_name": ""}

    # Equipos: primeros dos links a /startseite/verein/ con texto
    for a in soup.select("a[href*='startseite/verein']"):
        nombre = a.text.strip()
        if not nombre:
            continue
        if not result["home_name"]:
            result["home_name"] = nombre
        elif not result["away_name"] and nombre != result["home_name"]:
            result["away_name"] = nombre
            break

    # Goles: en #sb-tore, li.sb-aktion-heim / li.sb-aktion-gast
    tore = soup.find("div", id="sb-tore")
    if not tore:
        return result

    for li in tore.find_all("li"):
        classes = li.get("class", [])
        is_home_goal = any("heim" in c for c in classes)
        is_away_goal = any("gast" in c for c in classes)
        if not is_home_goal and not is_away_goal:
            continue

        aktion = li.find("div", class_="sb-aktion-aktion")
        if not aktion:
            continue
        text = aktion.get_text(" ", strip=True)
        player_a = aktion.find("a", class_="wichtig")
        if not player_a:
            continue
        nombre = player_a.text.strip()

        is_own = bool(re.search(r"propia puerta|propia meta|Eigentor|en propia", text, re.I))
        is_pen = bool(re.search(r"penal|penalty|Elfmeter|\(EP\)", text, re.I))
        tipo = "owngoal" if is_own else ("penalty" if is_pen else "regular")

        entry = {"nombre": nombre, "tipo": tipo}
        if is_home_goal:
            result["home"].append(entry)
        else:
            result["away"].append(entry)

    return result


def get_tm_all_matches(jornadas=range(1, 16)) -> list:
    """Retorna lista de partidos TM con goleadores para todas las jornadas."""
    all_matches = []
    for j in jornadas:
        match_ids = get_tm_jornada_match_ids(j)
        print(f"  J{j:>2}: {len(match_ids)} partidos encontrados")
        for mid, score_h, score_a in match_ids:
            goals = get_tm_goalscorers(mid)
            all_matches.append({
                "jornada": j,
                "tm_match_id": mid,
                "score_home": score_h,
                "score_away": score_a,
                "home": goals.get("home_name", ""),
                "away": goals.get("away_name", ""),
                "goles_home": goals.get("home", []),
                "goles_away": goals.get("away", []),
            })
            import time; time.sleep(0.4)
    return all_matches


# ─── SofaScore incidents (con filtro autogoles) ───────────────────────────────

def fetch_json(page, url):
    r = page.evaluate(f"""
        async () => {{
            try {{
                const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
                if (!resp.ok) return {{"_status": resp.status}};
                return await resp.json();
            }} catch(e) {{ return {{"_error": e.toString()}}; }}
        }}
    """)
    return r or {}


def get_ss_goalscorers(page, event_id):
    """Retorna {home: [{nombre, minuto}], away: [...]} sin autogoles."""
    data = fetch_json(page, f"https://api.sofascore.com/api/v1/event/{event_id}/incidents")
    home_goals, away_goals = [], []
    for inc in data.get("incidents", []):
        if inc.get("incidentType") not in ("goal", "penaltyScored"):
            continue
        if inc.get("incidentClass") == "ownGoal":
            continue
        p = inc.get("player", {})
        entry = {"nombre": p.get("name", ""), "minuto": inc.get("time"),
                 "tipo": "penalty" if inc.get("incidentClass") == "penalty" else "regular"}
        if inc.get("isHome"):
            home_goals.append(entry)
        else:
            away_goals.append(entry)
    return {"home": home_goals, "away": away_goals}


# ─── Cruce ────────────────────────────────────────────────────────────────────

def match_goalscorers(tm_list, ss_list):
    """
    Compara dos listas de goleadores (tm y ss).
    Retorna lista de discrepancias: jugadores en TM no encontrados en SS y viceversa.
    """
    tm_remaining = list(tm_list)
    ss_remaining = list(ss_list)
    matched_ss = [False] * len(ss_remaining)

    for tm_g in tm_remaining:
        for i, ss_g in enumerate(ss_remaining):
            if not matched_ss[i] and nombres_match(tm_g["nombre"], ss_g["nombre"]):
                matched_ss[i] = True
                break

    unmatched_tm = [g for g, m in zip(tm_list, [
        any(nombres_match(g["nombre"], ss_g["nombre"]) for ss_g in ss_list)
        for g in tm_list
    ]) if not m]

    unmatched_ss = [ss_list[i] for i, m in enumerate(matched_ss) if not m]

    return unmatched_tm, unmatched_ss


def cross_match_all(tm_matches, ss_by_fixture) -> list:
    """
    Cruza todos los partidos TM vs SS.
    Match por: equipos (nombres_match) + resultado idéntico.
    ss_by_fixture: dict (home, away) → {goals, score_home, score_away, jornada}
    """
    discrepancias = []

    # Deduplicar TM por match_id
    seen_tm_ids = set()
    unique_tm = []
    for m in tm_matches:
        mid = m["tm_match_id"]
        if mid not in seen_tm_ids:
            seen_tm_ids.add(mid)
            unique_tm.append(m)
    tm_matches = unique_tm

    matched_count = 0
    for tm in tm_matches:
        # Buscar partido en SS por equipos + resultado
        ss_entry = None
        j = tm["jornada"]
        for (sh, sa), data in ss_by_fixture.items():
            if not (nombres_match(tm["home"], sh) and nombres_match(tm["away"], sa)):
                continue
            # Verificar resultado (número de goles incluyendo autogoles)
            tm_sh = tm.get("score_home")
            tm_sa = tm.get("score_away")
            ss_sh = data.get("score_home")
            ss_sa = data.get("score_away")
            if tm_sh is not None and ss_sh is not None:
                if tm_sh != ss_sh or tm_sa != ss_sa:
                    continue  # mismo par de equipos pero resultado diferente → fixture distinto
            ss_entry = data
            j = data["jornada"]
            break

        if ss_entry is None:
            print(f"  J{tm['jornada']:>2} NO MATCH: {tm['home']} {tm.get('score_home','?')}:{tm.get('score_away','?')} {tm['away']}")
            continue

        matched_count += 1
        ss_goals = ss_entry["goals"]

        # Filtrar autogoles de TM
        tm_home_real = [g for g in tm["goles_home"] if g["tipo"] != "owngoal"]
        tm_away_real = [g for g in tm["goles_away"] if g["tipo"] != "owngoal"]

        for side, tm_list, ss_list in [
            ("home", tm_home_real, ss_goals.get("home", [])),
            ("away", tm_away_real, ss_goals.get("away", [])),
        ]:
            unmatched_tm, unmatched_ss = match_goalscorers(tm_list, ss_list)

            if unmatched_tm or unmatched_ss:
                discrepancias.append({
                    "jornada": j,
                    "partido": f"{tm['home']} vs {tm['away']}",
                    "resultado": f"{tm.get('score_home','?')}:{tm.get('score_away','?')}",
                    "lado": side,
                    "en_tm_no_en_ss": [g["nombre"] for g in unmatched_tm],
                    "en_ss_no_en_tm": [g["nombre"] for g in unmatched_ss],
                    "tm_goles": [g["nombre"] for g in tm_list],
                    "ss_goles": [g["nombre"] for g in ss_list],
                })

    print(f"  Partidos matcheados TM↔SS: {matched_count}/{len(unique_tm)}")
    return discrepancias


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright

    # ── 1. Scraping Transfermarkt ──
    print("=== PASO 1: Scraping Transfermarkt (goleadores por jornada) ===")
    tm_matches = get_tm_all_matches(range(1, 16))
    print(f"Total partidos TM: {len(tm_matches)}")
    with open("apertura2026_tm_goles.json", "w", encoding="utf-8") as f:
        json.dump(tm_matches, f, ensure_ascii=False, indent=2)
    print("Guardado en apertura2026_tm_goles.json")

    # ── 2. SofaScore incidents ──
    print("\n=== PASO 2: SofaScore incidents (filtro autogoles) ===")
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        base = json.load(f)
    finished = [p for p in base["partidos"] if p["estado"] == "finished"]

    ss_by_fixture = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-UY", viewport={"width": 1280, "height": 800},
        ).new_page()
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        for i, p in enumerate(finished, 1):
            goals = get_ss_goalscorers(page, p["id"])
            # Resultado: parsear "3-1" → (3, 1)
            res = p.get("resultado") or ""
            m = re.match(r"(\d+)-(\d+)", res)
            score_h = int(m.group(1)) if m else None
            score_a = int(m.group(2)) if m else None
            key = (p["local"], p["visitante"])
            ss_by_fixture[key] = {
                "goals": goals,
                "score_home": score_h,
                "score_away": score_a,
                "jornada": p["jornada"],
            }
            if i % 20 == 0:
                print(f"  {i}/{len(finished)} partidos")
            page.wait_for_timeout(100)
        browser.close()

    print(f"  Total partidos SS: {len(ss_by_fixture)}")

    # ── 3. Cruce ──
    print("\n=== PASO 3: Cruce TM vs SofaScore ===")
    discrepancias = cross_match_all(tm_matches, ss_by_fixture)

    # Filtrar: solo jornadas <= 14 (J15 puede tener datos incompletos)
    disc_confirmadas = [d for d in discrepancias if d["jornada"] <= 14]
    disc_j15         = [d for d in discrepancias if d["jornada"] == 15]

    print(f"\nDiscrepancias J1-J14: {len(disc_confirmadas)}")
    print(f"Discrepancias J15 (posible timing): {len(disc_j15)}")

    if disc_confirmadas:
        print("\n--- Discrepancias confirmadas (J1-J14) ---")
        for d in sorted(disc_confirmadas, key=lambda x: x["jornada"]):
            print(f"\n  J{d['jornada']:>2} | {d['partido']} ({d.get('resultado','?')}) | {d['lado'].upper()}")
            print(f"    TM dice:  {d['tm_goles']}")
            print(f"    SS dice:  {d['ss_goles']}")
            if d["en_tm_no_en_ss"]:
                print(f"    En TM pero NO en SS: {d['en_tm_no_en_ss']}")
            if d["en_ss_no_en_tm"]:
                print(f"    En SS pero NO en TM: {d['en_ss_no_en_tm']}")
    else:
        print("\n  Ninguna discrepancia en J1-J14.")

    output = {
        "fecha": __import__("datetime").date.today().isoformat(),
        "total_partidos_cruzados": len(tm_matches),
        "discrepancias_j1_j14": disc_confirmadas,
        "discrepancias_j15": disc_j15,
    }
    with open("apertura2026_cruce_tm_ss.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\nGuardado en apertura2026_cruce_tm_ss.json")


if __name__ == "__main__":
    main()
