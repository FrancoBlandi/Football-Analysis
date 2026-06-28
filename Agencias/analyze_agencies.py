#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_agencies.py — Análisis de agencias de representación a partir de player_profiles.json.

Genera:
  - agency_summary.json   : stats por agencia
  - players_enriched.json : jugadores con campos inferidos
  - agency_summary.csv    : tabla para Power BI / Excel
"""

import json, csv
from pathlib import Path
from datetime import date, datetime

PROFILES_PATH = Path(__file__).parent / "player_profiles.json"
ROSTERS_PATH  = Path(__file__).parent / "agency_rosters.json"
OUT_SUMMARY   = Path(__file__).parent / "agency_summary.json"
OUT_PLAYERS   = Path(__file__).parent / "players_enriched.json"
OUT_CSV       = Path(__file__).parent / "agency_summary.csv"

TODAY = date.today()
CURRENT_YEAR = TODAY.year


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except Exception:
        return None


def infer_agency_since(transfers, current_agency_id, agency_id_from_roster):
    """
    TM no expone cuándo un jugador se unió a su agencia actual.
    Heurística: la agencia actual probablemente gestionó la última transferencia.
    Retorna:
      - agency_since_approx: fecha ISO del último pase (lower bound)
      - agency_since_method: cómo se infirió
    """
    if not transfers:
        return None, "no_transfers"

    # Filtrar solo pases reales (no loans si queremos solo ventas)
    paid_transfers = [t for t in transfers if t.get("fee") and t["fee"] > 0 and not t.get("is_loan")]
    all_moves      = [t for t in transfers if t.get("date") and not t.get("is_loan")]
    loans          = [t for t in transfers if t.get("is_loan") and t.get("date")]

    if paid_transfers:
        last_paid = max(paid_transfers, key=lambda t: t.get("date") or "")
        return last_paid.get("date"), "last_paid_transfer"

    if all_moves:
        last_move = max(all_moves, key=lambda t: t.get("date") or "")
        return last_move.get("date"), "last_transfer"

    return None, "no_moves"


def career_stats(transfers):
    dates = [parse_date(t.get("date")) for t in transfers if t.get("date")]
    dates = [d for d in dates if d]
    if not dates:
        return None, None, None
    first = min(dates)
    last  = max(dates)
    years = round((last - first).days / 365.25, 1) if first != last else 0
    return str(first), str(last), years


def enrich_player(p, agency_id_from_roster=None):
    transfers = p.get("transfers", [])

    first_transfer, last_transfer, career_years = career_stats(transfers)

    agency_since, agency_since_method = infer_agency_since(
        transfers, p.get("tm_agency_id"), agency_id_from_roster
    )

    # Valor máximo de mercado registrado en transfers
    mv_at_transfers = [t.get("mv_at_transfer") for t in transfers if t.get("mv_at_transfer")]
    peak_mv = max(mv_at_transfers) if mv_at_transfers else None

    # First club que no sea argentino (primer export)
    ar_country_ids = {"9"}  # Argentina
    first_export_date = None
    first_export_club = None
    for t in sorted(transfers, key=lambda x: x.get("date") or ""):
        # Heuristic: if from Argentina to somewhere else
        if t.get("from_club") and t.get("to_club") and t.get("date"):
            # If destination club ID doesn't match known AR clubs
            # Use competition context if available — fallback: check club name
            pass  # Resolved below via transfer chain

    # Detect first international transfer (Argentina -> abroad)
    ar_keywords = ["argentina", "arg", "newell", "river", "boca", "racing", "independiente",
                   "san lorenzo", "huracan", "velez", "lanus", "banfield", "godoy", "talleres",
                   "estudiantes", "gimnasia", "rosario", "atletico tucuman", "colon", "union",
                   "aldosivi", "platense", "defensa", "arsenal", "tigre", "belgrano", "patronato"]

    def is_ar_club(name):
        if not name:
            return False
        nl = name.lower()
        return any(k in nl for k in ar_keywords)

    sorted_tr = sorted(transfers, key=lambda x: x.get("date") or "")
    for t in sorted_tr:
        if is_ar_club(t.get("from_club")) and not is_ar_club(t.get("to_club")) and t.get("to_club"):
            first_export_date = t.get("date")
            first_export_club = t.get("to_club")
            break

    enriched = {**p}
    enriched["first_transfer_date"]  = first_transfer
    enriched["last_transfer_date"]   = last_transfer
    enriched["career_years"]         = career_years
    enriched["agency_since_approx"]  = agency_since
    enriched["agency_since_method"]  = agency_since_method
    enriched["peak_mv"]              = peak_mv
    enriched["first_export_date"]    = first_export_date
    enriched["first_export_club"]    = first_export_club
    enriched["was_exported"]         = first_export_date is not None

    return enriched


def agency_stats(players):
    mv_list   = [p["market_value"] for p in players if p.get("market_value")]
    fees_list = [p["total_fees_received"] for p in players if p.get("total_fees_received") and p["total_fees_received"] > 0]
    exported  = [p for p in players if p.get("was_exported")]
    with_since = [p for p in players if p.get("agency_since_approx")]

    # Age from birth_date
    ages = []
    for p in players:
        bd = parse_date(p.get("birth_date"))
        if bd:
            ages.append((TODAY - bd).days / 365.25)

    stats = {
        "n_players":        len(players),
        "n_exported":       len(exported),
        "pct_exported":     round(len(exported) / len(players) * 100, 1) if players else 0,
        "total_mv":         sum(mv_list),
        "avg_mv":           round(sum(mv_list) / len(mv_list)) if mv_list else 0,
        "median_mv":        sorted(mv_list)[len(mv_list)//2] if mv_list else 0,
        "top_player_mv":    max(mv_list) if mv_list else 0,
        "total_fees_generated": sum(fees_list),
        "avg_fees_per_player": round(sum(fees_list) / len(players)) if players else 0,
        "n_with_fees":      len(fees_list),
        "avg_age":          round(sum(ages) / len(ages), 1) if ages else None,
        "players_top5_mv":  [
            {"name": p["name"], "mv": p.get("market_value"), "club": p.get("club")}
            for p in sorted(players, key=lambda x: x.get("market_value") or 0, reverse=True)[:5]
        ],
        "agency_since_coverage": round(len(with_since) / len(players) * 100, 1) if players else 0,
    }
    return stats


def main():
    with open(PROFILES_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    with open(ROSTERS_PATH, encoding="utf-8") as f:
        rosters = json.load(f)

    # Build agency_id lookup from rosters
    agency_id_map = {}
    for agency_name, data in rosters.items():
        for p in data.get("players", []):
            if p.get("tm_id"):
                agency_id_map[str(p["tm_id"])] = data.get("tm_id")

    # Enrich all players
    enriched = {}
    for key, p in profiles.items():
        if p.get("error"):
            enriched[key] = p
            continue
        enriched[key] = enrich_player(p, agency_id_map.get(str(p.get("tm_id"))))

    with open(OUT_PLAYERS, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"players_enriched.json -> {len(enriched)} jugadores")

    # Group by agency
    by_agency = {}
    for p in enriched.values():
        if p.get("error"):
            continue
        ag = p.get("agency", "Unknown")
        by_agency.setdefault(ag, []).append(p)

    # Per-agency summary
    summary = {}
    for ag, players in by_agency.items():
        summary[ag] = agency_stats(players)

    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"agency_summary.json -> {len(summary)} agencias")

    # CSV
    rows = []
    for ag, s in sorted(summary.items(), key=lambda x: -x[1]["total_mv"]):
        rows.append({
            "Agencia":              ag,
            "Jugadores":            s["n_players"],
            "Exportados":           s["n_exported"],
            "% Exportados":         s["pct_exported"],
            "Valor Total (M€)":     round(s["total_mv"] / 1e6, 2),
            "Valor Promedio (M€)":  round(s["avg_mv"] / 1e6, 2),
            "Top MV (M€)":          round(s["top_player_mv"] / 1e6, 2),
            "Fees Generados (M€)":  round(s["total_fees_generated"] / 1e6, 2),
            "Fees Prom x Jugador (€)": s["avg_fees_per_player"],
            "Edad Promedio":        s["avg_age"],
        })

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"agency_summary.csv -> {len(rows)} filas")

    # Print summary to console
    print("\n--- Ranking por Valor de Mercado Total ---")
    print(f"{'Agencia':<25} {'Jugadores':>9} {'Exportados':>10} {'MV Total':>12} {'Fees Total':>12} {'Top Player':>12}")
    print("-" * 85)
    for ag, s in sorted(summary.items(), key=lambda x: -x[1]["total_mv"]):
        top = s["players_top5_mv"][0] if s["players_top5_mv"] else {}
        print(
            f"{ag:<25} {s['n_players']:>9} {s['n_exported']:>10} "
            f"{s['total_mv']/1e6:>11.1f}M {s['total_fees_generated']/1e6:>11.1f}M "
            f"  {top.get('name','')[:20]} ({(top.get('mv') or 0)/1e6:.1f}M)"
        )


if __name__ == "__main__":
    main()
