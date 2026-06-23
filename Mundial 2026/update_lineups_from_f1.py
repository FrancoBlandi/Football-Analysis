#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_lineups_from_f1.py — Propaga lineups reales de fecha 1 a fechas 2 y 3.

Fuentes:
  - wc2026_wc_results.json  → stats por jugador (rating, mins)
  - f1_subs_in.json         → quién entró como suplente y en qué minuto (scraped desde incidents)

Reglas:
  - rating != None  Y  NO entró como suplente → "starter"     (Titular, p_over60=0.92)
  - entró como suplente antes del min 60      → "rotacional"   (p_over60=0.45)
  - entró como suplente desde el min 60       → "substitute"   (Suplente, p_over60=0.08)
  - rating == None (no jugó, banquillo)        → "rotacional"   (p_over60=0.45)
  - no aparece en wc_results                  → "rotacional"   (p_over60=0.45)
  - roja directa en F1                        → "missing"      solo para F2

Uso:
    python "Mundial 2026/update_lineups_from_f1.py"
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR            = Path(__file__).parent
WC_RESULTS_PATH     = BASE_DIR / "wc2026_wc_results.json"
LINEUPS_PATH        = BASE_DIR / "wc2026_lineups.json"
FIXTURES_PATH       = BASE_DIR / "wc2026_fixtures.json"
SQUADS_PATH         = BASE_DIR / "wc2026_squads.json"
SUBS_IN_PATH        = BASE_DIR / "f1_subs_in.json"
INJURED_OUT_PATH    = BASE_DIR / "f1_injured_out.json"

# Suplente que entró antes del min 60 → rotacional; desde min 60 → suplente
ROTACIONAL_ENTRY_CUTOFF = 60


def main():
    wc_results = json.load(open(WC_RESULTS_PATH, encoding="utf-8"))
    lineups    = json.load(open(LINEUPS_PATH,    encoding="utf-8")) if LINEUPS_PATH.exists() else {}
    fixtures   = json.load(open(FIXTURES_PATH,   encoding="utf-8")).get("fixtures", [])
    squads     = json.load(open(SQUADS_PATH,     encoding="utf-8"))

    subs_in_data = {}
    if SUBS_IN_PATH.exists():
        subs_in_data = json.load(open(SUBS_IN_PATH, encoding="utf-8"))
        print(f"[subs_in] datos disponibles para {len(subs_in_data)} partidos F1")
    else:
        print("[subs_in] WARN: f1_subs_in.json no existe.")

    injured_out_data = {}
    if INJURED_OUT_PATH.exists():
        injured_out_data = json.load(open(INJURED_OUT_PATH, encoding="utf-8"))
        n_inj = sum(len(v) for v in injured_out_data.values())
        print(f"[injured] {n_inj} jugadores lesionados en {len(injured_out_data)} partidos F1")

    # ── Índices de fixtures F2 y F3 por team_id ──────────────────────────────
    fecha2_by_tid, fecha3_by_tid = {}, {}
    for fx in fixtures:
        tid_h, tid_a = fx.get("home_id"), fx.get("away_id")
        if fx.get("round_num") == 2:
            if tid_h: fecha2_by_tid[tid_h] = fx
            if tid_a: fecha2_by_tid[tid_a] = fx
        elif fx.get("round_num") == 3:
            if tid_h: fecha3_by_tid[tid_h] = fx
            if tid_a: fecha3_by_tid[tid_a] = fx

    # team_id → team_name (para lookup inverso)
    tid_to_name = {}
    for fx in fixtures:
        tid_to_name[fx.get("home_id")] = fx.get("home_name","")
        tid_to_name[fx.get("away_id")] = fx.get("away_name","")

    # ── Squads: {team_name → set(pid_str)} ───────────────────────────────────
    squad_pids_by_team = {
        tname: {str(p["id"]) for p in tdata.get("players", []) if p.get("id")}
        for tname, tdata in squads.items()
    }

    def get_or_create_entry(fx_dest):
        eid_str = str(fx_dest["event_id"])
        if eid_str not in lineups:
            lineups[eid_str] = {
                "event_id":  fx_dest["event_id"],
                "home":      fx_dest.get("home_name", ""),
                "away":      fx_dest.get("away_name", ""),
                "group":     fx_dest.get("group", ""),
                "round_num": fx_dest["round_num"],
                "confirmed": False,
                "players":   {},
            }
        return lineups[eid_str]

    updated_teams = 0

    for eid_str, md in wc_results.get("matches", {}).items():
        if md.get("round_num") != 1:
            continue

        home_name    = md["home"]
        away_name    = md["away"]
        home_id      = md["home_id"]
        away_id      = md["away_id"]
        player_stats = md.get("player_stats", {})

        # Suplentes que entraron (pid → minuto) y lesionados que salieron (pid → True)
        match_subs_in    = subs_in_data.get(eid_str, {})
        match_injured_out = injured_out_data.get(eid_str, {})

        # Bajas por roja directa → missing para F2
        suspended_f2 = set()
        for miss in md.get("incidents", {}).get("missing_next", []):
            pid = miss.get("player_id")
            if pid:
                suspended_f2.add(str(pid))
                team = home_name if miss.get("is_home") else away_name
                print(f"  [baja F2] {miss.get('player_name','')} ({team}) suspension")

        for tid, team_name in [(home_id, home_name), (away_id, away_name)]:
            is_home    = (tid == home_id)
            squad_pids = squad_pids_by_team.get(team_name, set())

            # Stats de jugadores de este equipo en F1
            team_stats = {
                pid: pst for pid, pst in player_stats.items()
                if pst.get("is_home") == is_home
            }
            f1_pids = set(team_stats.keys())

            # Determinar status para F2/F3
            player_statuses = {}
            for pid_str, pst in team_stats.items():
                name   = pst.get("name", "")
                mins   = pst.get("mins", 0) or 0
                rating = pst.get("rating")

                if rating is None:
                    # En el partido pero no jugó (banquillo sin entrar)
                    new_status = "rotacional"
                elif pid_str in match_subs_in:
                    # Entró como suplente — distinguir por minuto de entrada
                    entry_min = match_subs_in[pid_str]
                    if entry_min < ROTACIONAL_ENTRY_CUTOFF:
                        new_status = "rotacional"   # entró antes del 60': jugó bastante
                    else:
                        new_status = "substitute"   # entró desde el 60': poca carga
                elif pid_str in match_injured_out and pid_str not in match_subs_in:
                    # Titular que salió lesionado → se mantiene como starter
                    # (sin dato de gravedad no se puede asumir baja; usar BAJA_OVERRIDES para confirmados)
                    new_status = "starter"
                else:
                    # Jugó y NO entró como suplente → titular real
                    new_status = "starter"

                player_statuses[pid_str] = {
                    "status":  new_status,
                    "name":    name,
                    "f1_mins": mins,
                }

            for round_dest, fecha_by_tid in [(2, fecha2_by_tid), (3, fecha3_by_tid)]:
                fx_dest = fecha_by_tid.get(tid)
                if not fx_dest:
                    continue

                entry = get_or_create_entry(fx_dest)
                ep    = entry["players"]
                added = 0

                for pid_str, pdata in player_statuses.items():
                    existing = ep.get(pid_str, {})
                    if existing.get("from_wc_result") and existing.get("reason") == "suspension":
                        continue

                    if round_dest == 2 and pid_str in suspended_f2:
                        ep[pid_str] = {
                            "status":  "missing",
                            "name":    pdata["name"],
                            "from_f1": True,
                            "reason":  "suspension",
                        }
                        added += 1
                        continue

                    ep[pid_str] = {
                        "status":  pdata["status"],
                        "name":    pdata["name"],
                        "from_f1": True,
                        "f1_mins": pdata["f1_mins"],
                    }
                    added += 1

                # Squad no en wc_results → rotacional
                for pid_str in squad_pids - f1_pids:
                    existing = ep.get(pid_str, {})
                    if existing.get("from_wc_result") and existing.get("reason") == "suspension":
                        continue
                    if existing.get("from_f1"):
                        continue
                    ep[pid_str] = {
                        "status":  "rotacional",
                        "name":    "",
                        "from_f1": True,
                        "reason":  "no_en_wc_results",
                    }
                    added += 1

                if added:
                    updated_teams += 1
                    team_pids = f1_pids | squad_pids
                    n_s   = sum(1 for pid, p in ep.items() if p.get("status") == "starter"   and pid in team_pids)
                    n_rot = sum(1 for pid, p in ep.items() if p.get("status") == "rotacional" and pid in team_pids)
                    n_sub = sum(1 for pid, p in ep.items() if p.get("status") == "substitute" and pid in team_pids)
                    n_b   = sum(1 for pid, p in ep.items() if p.get("status") == "missing"    and pid in team_pids)
                    print(f"  {team_name} -> F{round_dest}: "
                          f"{n_s} titulares | {n_rot} rotacionales | {n_sub} suplentes | {n_b} bajas")

                entry["players"] = ep

    # ── Propagar F2 → F3 (sobreescribe lo que vino de F1 con datos más recientes) ─
    print("\nPropagando F2 -> F3...")
    for eid_str, md in wc_results.get("matches", {}).items():
        if md.get("round_num") != 2:
            continue

        home_name    = md["home"]
        away_name    = md["away"]
        home_id      = md["home_id"]
        away_id      = md["away_id"]
        player_stats = md.get("player_stats", {})

        match_subs_in     = subs_in_data.get(eid_str, {})
        match_injured_out = injured_out_data.get(eid_str, {})

        suspended_f3 = set()
        for miss in md.get("incidents", {}).get("missing_next", []):
            pid = miss.get("player_id")
            if pid:
                suspended_f3.add(str(pid))
                team = home_name if miss.get("is_home") else away_name
                print(f"  [baja F3] {miss.get('player_name','')} ({team}) suspension")

        for tid, team_name in [(home_id, home_name), (away_id, away_name)]:
            is_home    = (tid == home_id)
            squad_pids = squad_pids_by_team.get(team_name, set())

            team_stats = {
                pid: pst for pid, pst in player_stats.items()
                if pst.get("is_home") == is_home
            }
            f2_pids = set(team_stats.keys())

            player_statuses = {}
            for pid_str, pst in team_stats.items():
                name   = pst.get("name", "")
                mins   = pst.get("mins", 0) or 0
                rating = pst.get("rating")
                # Usar status del wc_result directamente (scrape_f2 ya lo guarda como "starter"/"sub_in")
                raw_status = pst.get("status", "starter")

                if rating is None:
                    new_status = "rotacional"
                elif raw_status == "sub_in":
                    # Suplente: si jugó 30+ min es rotacional, si no es suplente
                    new_status = "rotacional" if mins >= 30 else "substitute"
                else:
                    new_status = "starter"

                player_statuses[pid_str] = {"status": new_status, "name": name, "f2_mins": mins}

            fx3 = fecha3_by_tid.get(tid)
            if not fx3:
                continue

            entry = get_or_create_entry(fx3)
            ep    = entry["players"]
            added = 0

            for pid_str, pdata in player_statuses.items():
                existing = ep.get(pid_str, {})
                if existing.get("from_wc_result") and existing.get("reason") == "suspension":
                    continue

                if pid_str in suspended_f3:
                    ep[pid_str] = {"status": "missing", "name": pdata["name"],
                                   "from_f2": True, "reason": "suspension"}
                    added += 1
                    continue

                ep[pid_str] = {"status": pdata["status"], "name": pdata["name"],
                               "from_f2": True, "f2_mins": pdata["f2_mins"]}
                added += 1

            for pid_str in squad_pids - f2_pids:
                existing = ep.get(pid_str, {})
                if existing.get("from_wc_result") and existing.get("reason") == "suspension":
                    continue
                ep[pid_str] = {"status": "rotacional", "name": "", "from_f2": True,
                               "reason": "no_en_wc_results_f2"}
                added += 1

            if added:
                updated_teams += 1
                team_pids = f2_pids | squad_pids
                n_s   = sum(1 for pid, p in ep.items() if p.get("status") == "starter"   and pid in team_pids)
                n_rot = sum(1 for pid, p in ep.items() if p.get("status") == "rotacional" and pid in team_pids)
                n_sub = sum(1 for pid, p in ep.items() if p.get("status") == "substitute" and pid in team_pids)
                n_b   = sum(1 for pid, p in ep.items() if p.get("status") == "missing"    and pid in team_pids)
                print(f"  {team_name} -> F3: {n_s} titulares | {n_rot} rotacionales | {n_sub} suplentes | {n_b} bajas")

            entry["players"] = ep

    json.dump(lineups, open(LINEUPS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nLineups actualizados: {updated_teams} entradas de equipo")
    for rn in (1, 2, 3):
        cnt = sum(1 for v in lineups.values() if v.get("round_num") == rn)
        if cnt:
            print(f"  Fecha {rn}: {cnt} partidos en lineups.json")


if __name__ == "__main__":
    main()
