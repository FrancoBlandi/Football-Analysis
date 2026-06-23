#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_f3_lineups_from_f2.py — Escribe los lineups de F3 directamente desde los starters de F2.

Regla simple:
  - Top 11 jugadores por minutesPlayed en F2 = "starter" para F3
  - Resto del squad = "rotacional" para F3
  - Suspendidos (missing_next de F2) = "missing" para F3
  - No hay cascada desde F1 — F3 se escribe limpio desde F2
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR      = Path(__file__).parent
WC_RESULTS    = BASE_DIR / "wc2026_wc_results.json"
FIXTURES_PATH = BASE_DIR / "wc2026_fixtures.json"
SQUADS_PATH   = BASE_DIR / "wc2026_squads.json"
LINEUPS_PATH  = BASE_DIR / "wc2026_lineups.json"

# Bajas confirmadas manualmente (pid: razón)
MANUAL_BAJA = {
    1134351: "Ismael Koné (Canada) — lesión confirmada",
}


def main():
    wc     = json.load(open(WC_RESULTS,    encoding="utf-8"))
    fix    = json.load(open(FIXTURES_PATH, encoding="utf-8"))["fixtures"]
    squads = json.load(open(SQUADS_PATH,   encoding="utf-8"))
    lu     = json.load(open(LINEUPS_PATH,  encoding="utf-8"))

    # Índice de fixtures F3 por team_id
    f3_by_tid = {}
    for fx in fix:
        if fx.get("round_num") == 3:
            if fx.get("home_id"): f3_by_tid[fx["home_id"]] = fx
            if fx.get("away_id"): f3_by_tid[fx["away_id"]] = fx

    # Squad pids por equipo
    squad_by_name = {
        name: {str(p["id"]) for p in tdata.get("players", []) if p.get("id")}
        for name, tdata in squads.items()
    }

    processed = 0

    for eid_str, md in wc["matches"].items():
        if md.get("round_num") != 2:
            continue

        home_id   = md["home_id"]
        away_id   = md["away_id"]
        home_name = md["home"]
        away_name = md["away"]
        pstats    = md.get("player_stats", {})

        # Suspendidos para F3
        suspended_f3 = {}
        for miss in md.get("incidents", {}).get("missing_next", []):
            pid = miss.get("player_id")
            if pid:
                suspended_f3[str(pid)] = {
                    "name":   miss.get("player_name", ""),
                    "is_home": miss.get("is_home", True),
                    "reason": "suspension",
                }

        for tid, team_name in [(home_id, home_name), (away_id, away_name)]:
            fx3 = f3_by_tid.get(tid)
            if not fx3:
                continue

            is_home    = (tid == home_id)
            squad_pids = squad_by_name.get(team_name, set())

            # Jugadores del equipo que jugaron en F2, ordenados por mins desc
            team_played = [
                (pid, p) for pid, p in pstats.items()
                if p.get("is_home") == is_home and (p.get("mins") or 0) > 0
            ]
            team_played.sort(key=lambda x: x[1].get("mins", 0), reverse=True)

            # Top 11 = starters
            starters = {pid for pid, _ in team_played[:11]}

            # Construir entrada de lineup para F3 desde cero
            eid3_str = str(fx3["event_id"])
            if eid3_str not in lu:
                lu[eid3_str] = {
                    "event_id":  fx3["event_id"],
                    "home":      fx3.get("home_name", ""),
                    "away":      fx3.get("away_name", ""),
                    "group":     fx3.get("group", ""),
                    "round_num": 3,
                    "confirmed": False,
                    "players":   {},
                }
            ep = lu[eid3_str]["players"]

            # Limpiar entradas previas de ESTE equipo antes de reasignar
            all_team_pids = squad_pids | {pid for pid, _ in team_played}
            for pid_str in list(ep.keys()):
                if pid_str in all_team_pids:
                    del ep[pid_str]

            # Suspendidos primero (no se sobreescriben)
            for pid_str, sdata in suspended_f3.items():
                if (sdata["is_home"] == is_home) or True:  # ambos lados pueden estar en este dict
                    # filtrar por team_id del incidente
                    pass
            # Re-filtrar suspendidos por equipo correcto
            my_team_id = tid
            for miss in md.get("incidents", {}).get("missing_next", []):
                pid  = miss.get("player_id")
                miss_tid = miss.get("team_id")
                if pid and miss_tid == my_team_id:
                    ep[str(pid)] = {
                        "status": "missing",
                        "name":   miss.get("player_name", ""),
                        "from_f2": True,
                        "reason": "suspension",
                    }

            # Bajas manuales
            for pid_int, razon in MANUAL_BAJA.items():
                if str(pid_int) in squad_pids:
                    ep[str(pid_int)] = {
                        "status": "missing",
                        "name":   razon,
                        "from_f2": True,
                        "reason": "baja_manual",
                    }

            # Starters (top 11 por mins en F2)
            for pid_str, p in team_played[:11]:
                if ep.get(pid_str, {}).get("status") == "missing":
                    continue
                ep[pid_str] = {
                    "status":   "starter",
                    "name":     p.get("name", ""),
                    "from_f2":  True,
                    "f2_mins":  p.get("mins", 0),
                }

            # Subs activos (posiciones 12+ en team_played)
            for pid_str, p in team_played[11:]:
                if ep.get(pid_str, {}).get("status") in ("missing", "starter"):
                    continue
                ep[pid_str] = {
                    "status":  "sub_in",
                    "name":    p.get("name", ""),
                    "from_f2": True,
                    "f2_mins": p.get("mins", 0),
                }

            # Resto del squad = rotacional
            played_pids = {pid for pid, _ in team_played}
            for pid_str in squad_pids - played_pids:
                if ep.get(pid_str, {}).get("status") in ("missing", "starter"):
                    continue
                ep[pid_str] = {
                    "status":  "rotacional",
                    "name":    "",
                    "from_f2": True,
                    "reason":  "no_jugó_f2",
                }

            lu[eid3_str]["players"] = ep

            n_s   = sum(1 for p in ep.values() if p.get("status") == "starter")
            n_sub = sum(1 for p in ep.values() if p.get("status") == "sub_in")
            n_rot = sum(1 for p in ep.values() if p.get("status") == "rotacional")
            n_b   = sum(1 for p in ep.values() if p.get("status") == "missing")
            print(f"  {team_name} -> F3: {n_s} titulares | {n_sub} subs | {n_rot} rotacionales | {n_b} bajas")
            processed += 1

    json.dump(lu, open(LINEUPS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nLineups F3 escritos: {processed} equipos")


if __name__ == "__main__":
    main()
