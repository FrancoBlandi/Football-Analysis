"""
chequear_asistencias.py — Verifica discrepancias de asistencias y goles (ambas direcciones)
entre incidents y lineups para todos los partidos del Apertura 2026.

Extiende la lógica de apertura_goles.py para capturar también assist1 de cada gol,
y cruza contra lineups.statistics.assists.
"""

import sys, io, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def fetch_json(page, url):
    result = page.evaluate(f"""
        async () => {{
            try {{
                const resp = await fetch('{url}', {{headers: {{Accept: 'application/json'}}}});
                if (!resp.ok) return {{"_status": resp.status}};
                return await resp.json();
            }} catch(e) {{
                return {{"_error": e.toString()}};
            }}
        }}
    """)
    return result or {}


def get_incidents_stats(page, event_id):
    """
    Devuelve conteo de goles y asistencias por jugador desde incidents.
    Captura scorer + assist1 (asistencia primaria).
    """
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/incidents"
    data = fetch_json(page, url)

    goles    = defaultdict(lambda: {"nombre": "", "count": 0})
    asists   = defaultdict(lambda: {"nombre": "", "count": 0})

    for inc in data.get("incidents", []):
        tipo = inc.get("incidentType", "")
        if tipo not in ("goal", "penaltyScored"):
            continue

        scorer = inc.get("player", {})
        pid_s  = scorer.get("id")
        if pid_s:
            goles[pid_s]["count"]  += 1
            goles[pid_s]["nombre"]  = scorer.get("name", "")

        assist = inc.get("assist1", {})
        pid_a  = assist.get("id") if assist else None
        if pid_a:
            asists[pid_a]["count"] += 1
            asists[pid_a]["nombre"] = assist.get("name", "")

    return goles, asists


def get_lineups_stats(page, event_id):
    """
    Devuelve conteo de goles y asistencias por jugador desde lineups.statistics.
    """
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    data = fetch_json(page, url)

    goles  = {}
    asists = {}
    for side in ["home", "away"]:
        for entry in data.get(side, {}).get("players", []):
            p     = entry.get("player", {})
            pid   = p.get("id")
            if not pid:
                continue
            stats = entry.get("statistics") or {}
            nombre = p.get("name", "")
            g = stats.get("goals", 0) or 0
            a = stats.get("goalAssist", 0) or stats.get("assists", 0) or 0
            if g:
                goles[pid]  = {"nombre": nombre, "count": g}
            if a:
                asists[pid] = {"nombre": nombre, "count": a}
    return goles, asists


def cross_check(inc_dict, lin_dict, stat_name):
    """
    Cruza incidents vs lineups en ambas direcciones.
    Devuelve lista de discrepancias: {player_id, nombre, incidents, lineups, diff}
    diff > 0 → incidents tiene más → jugador subestimado
    diff < 0 → lineups tiene más  → jugador sobreestimado
    """
    all_pids = set(inc_dict) | set(lin_dict)
    discs = []
    for pid in all_pids:
        n_inc = inc_dict.get(pid, {}).get("count", 0)
        n_lin = lin_dict.get(pid, {}).get("count", 0)
        if n_inc != n_lin:
            nombre = (inc_dict.get(pid) or lin_dict.get(pid, {})).get("nombre", str(pid))
            discs.append({
                "player_id": pid,
                "nombre":    nombre,
                "stat":      stat_name,
                "incidents": n_inc,
                "lineups":   n_lin,
                "diferencia": n_inc - n_lin,
                "direccion": "subestimado" if n_inc > n_lin else "sobreestimado",
            })
    return discs


def main():
    with open("apertura2026_goles.json", encoding="utf-8") as f:
        data = json.load(f)

    finished = [p for p in data["partidos"] if p["estado"] == "finished"]
    print(f"Partidos a analizar: {len(finished)}")

    from playwright.sync_api import sync_playwright

    all_discrepancias = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-UY",
            viewport={"width": 1280, "height": 800},
        ).new_page()

        print("Cargando SofaScore...")
        page.goto("https://www.sofascore.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        for i, partido in enumerate(finished, 1):
            ev_id   = partido["id"]
            jornada = partido["jornada"]
            fecha   = partido["fecha"]
            local   = partido["local"]
            visitante = partido["visitante"]

            g_inc, a_inc = get_incidents_stats(page, ev_id)
            g_lin, a_lin = get_lineups_stats(page, ev_id)

            disc_g = cross_check(g_inc, g_lin, "goles")
            disc_a = cross_check(a_inc, a_lin, "asistencias")

            for d in disc_g + disc_a:
                d.update({"event_id": ev_id, "jornada": jornada,
                          "fecha": fecha, "partido": f"{local} vs {visitante}"})
                all_discrepancias.append(d)

            if disc_g or disc_a:
                flags = []
                if disc_g:
                    sub_g  = [d for d in disc_g if d["diferencia"] > 0]
                    sobre_g = [d for d in disc_g if d["diferencia"] < 0]
                    if sub_g:  flags.append(f"GOLES sub: {', '.join(d['nombre'] for d in sub_g)}")
                    if sobre_g: flags.append(f"GOLES sobre: {', '.join(d['nombre'] for d in sobre_g)}")
                if disc_a:
                    sub_a  = [d for d in disc_a if d["diferencia"] > 0]
                    sobre_a = [d for d in disc_a if d["diferencia"] < 0]
                    if sub_a:  flags.append(f"ASIST sub: {', '.join(d['nombre'] for d in sub_a)}")
                    if sobre_a: flags.append(f"ASIST sobre: {', '.join(d['nombre'] for d in sobre_a)}")
                print(f"  J{jornada:>2} {fecha} {local[:14]} vs {visitante[:14]} *** {' | '.join(flags)}")
            else:
                if i % 20 == 0:
                    print(f"  [{i}/{len(finished)} partidos procesados, sin discrepancias acumuladas]")

            page.wait_for_timeout(130)

        browser.close()

    # Separar por dirección y stat
    sub_goles   = [d for d in all_discrepancias if d["stat"] == "goles"        and d["diferencia"] > 0]
    sobre_goles = [d for d in all_discrepancias if d["stat"] == "goles"        and d["diferencia"] < 0]
    sub_asist   = [d for d in all_discrepancias if d["stat"] == "asistencias"  and d["diferencia"] > 0]
    sobre_asist = [d for d in all_discrepancias if d["stat"] == "asistencias"  and d["diferencia"] < 0]

    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"  Goles subestimados   (incidents > lineups): {len(sub_goles)} casos")
    print(f"  Goles sobreestimados (lineups > incidents): {len(sobre_goles)} casos")
    print(f"  Asist subestimadas   (incidents > lineups): {len(sub_asist)} casos")
    print(f"  Asist sobreestimadas (lineups > incidents): {len(sobre_asist)} casos")

    def print_table(rows, titulo):
        if not rows:
            print(f"\n  {titulo}: ninguno")
            return
        print(f"\n  {titulo}:")
        print(f"  {'J':>3}  {'Fecha':<11}  {'Jugador':<30}  {'inc':>4}  {'lin':>4}  {'diff':>5}  Partido")
        for d in sorted(rows, key=lambda x: x["jornada"]):
            jornada = d.get("jornada", "?")
            j_str = f"J{jornada}" if isinstance(jornada, int) and jornada <= 14 else f"J{jornada}*"
            print(f"  {j_str:>3}  {d['fecha']:<11}  {d['nombre']:<30}  "
                  f"{d['incidents']:>4}  {d['lineups']:>4}  {d['diferencia']:>+5}  {d['partido']}")

    print_table(sub_goles,   "GOLES subestimados (faltan en lineups)")
    print_table(sobre_goles, "GOLES sobreestimados (sobran en lineups)")
    print_table(sub_asist,   "ASISTENCIAS subestimadas (faltan en lineups)")
    print_table(sobre_asist, "ASISTENCIAS sobreestimadas (sobran en lineups)")

    with open("apertura2026_discrepancias_full.json", "w", encoding="utf-8") as f:
        json.dump({
            "total": len(all_discrepancias),
            "goles_subestimados":    sub_goles,
            "goles_sobreestimados":  sobre_goles,
            "asist_subestimadas":    sub_asist,
            "asist_sobreestimadas":  sobre_asist,
        }, f, ensure_ascii=False, indent=2)

    print("\nGuardado en apertura2026_discrepancias_full.json")


if __name__ == "__main__":
    main()
