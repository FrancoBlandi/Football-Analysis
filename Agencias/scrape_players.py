#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_players.py — Fetch perfil completo de cada jugador via TM JSON API.

Para cada jugador extrae:
  - Historial de transferencias (fecha, de, a, fee, market_value)
  - Datos de perfil (edad, nacionalidad, posicion, agencia actual)

Output: Agencias/player_profiles.json

Uso:
    python Agencias/scrape_players.py
    python Agencias/scrape_players.py --resume
"""

import json, time, random, argparse, sys
from pathlib import Path

ROSTERS_PATH = Path(__file__).parent / "agency_rosters.json"
OUT_PATH     = Path(__file__).parent / "player_profiles.json"

BASE_URL  = "https://www.transfermarkt.us"
TMAPI     = "https://tmapi-alpha.transfermarkt.technology"
UA        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

CLUB_CACHE = {}


def api_get(page, url, retries=3):
    for attempt in range(retries):
        try:
            resp = page.request.get(url, timeout=15000)
            if resp.ok:
                return resp.json()
        except Exception as e:
            print(f"    warn ({attempt+1}): {e}")
            time.sleep(3 + attempt * 2)
    return None


def resolve_clubs(page, club_ids):
    """Fetch club names for a list of IDs, using cache."""
    missing = [cid for cid in club_ids if cid not in CLUB_CACHE]
    if missing:
        chunk = "&".join(f"ids[]={cid}" for cid in missing[:30])
        data = api_get(page, f"{TMAPI}/clubs?{chunk}")
        if data and data.get("success"):
            for club in data.get("data", []):
                CLUB_CACHE[club["id"]] = club.get("name", "")
        for cid in missing:
            CLUB_CACHE.setdefault(cid, "")
    return {cid: CLUB_CACHE.get(cid, "") for cid in club_ids}


def fetch_player_profile(page, player):
    tm_id = player.get("tm_id")
    if not tm_id:
        return None

    # --- Players API: profile + agency ---
    player_data = api_get(page, f"{TMAPI}/players?ids[]={tm_id}")
    p_attrs = {}
    if player_data and player_data.get("success") and player_data.get("data"):
        p = player_data["data"][0]
        attrs = p.get("attributes", {})
        life  = p.get("lifeDates", {})
        nat   = p.get("nationalityDetails", {}).get("nationalities", {})
        p_attrs = {
            "birth_date":          life.get("dateOfBirth"),
            "tm_agency_current":   attrs.get("consultantAgency", {}).get("name"),
            "tm_agency_id":        attrs.get("consultantAgencyId"),
            "contract_end":        attrs.get("contractUntil"),
            "position":            attrs.get("position", {}).get("name", player.get("position", "")),
            "nationality_id":      nat.get("nationalityId"),
        }

    profile = {
        "tm_id":        tm_id,
        "name":         player["name"],
        "agency":       player["agency"],
        "club":         player.get("club", ""),
        "position":     p_attrs.get("position") or player.get("position", ""),
        "market_value": player.get("market_value"),
        "contract_end": p_attrs.get("contract_end") or player.get("contract_end", ""),
        "birth_date":   p_attrs.get("birth_date"),
        "nationality":  player.get("nationality", ""),
        "tm_agency_current": p_attrs.get("tm_agency_current"),
        "tm_agency_id":      p_attrs.get("tm_agency_id"),
    }

    # --- Transfer history API ---
    th_data = api_get(page, f"{TMAPI}/transfer/history/player/{tm_id}")
    transfers = []
    if th_data and th_data.get("success"):
        history = th_data.get("data", {}).get("history", {})
        all_transfers = history.get("terminated", []) + history.get("pending", [])

        # Collect all club IDs to resolve in one batch
        club_ids = set()
        for t in all_transfers:
            src  = t.get("transferSource", {})
            dst  = t.get("transferDestination", {})
            if src.get("clubId"):  club_ids.add(str(src["clubId"]))
            if dst.get("clubId"):  club_ids.add(str(dst["clubId"]))
        clubs = resolve_clubs(page, list(club_ids))

        for t in all_transfers:
            src     = t.get("transferSource", {})
            dst     = t.get("transferDestination", {})
            details = t.get("details", {})
            fee_obj = details.get("fee") or {}
            mv_obj  = details.get("marketValue") or {}

            from_club = clubs.get(str(src.get("clubId", "")), "")
            to_club   = clubs.get(str(dst.get("clubId", "")), "")
            date_str  = details.get("date", "")[:10] if details.get("date") else ""
            season    = details.get("season", {}).get("display", "")
            fee_val   = fee_obj.get("value")
            mv_val    = mv_obj.get("value")
            is_loan   = t.get("typeDetails", {}).get("type") == "LOAN"

            transfers.append({
                "season":       season,
                "date":         date_str,
                "from_club":    from_club,
                "from_club_id": str(src.get("clubId", "")),
                "to_club":      to_club,
                "to_club_id":   str(dst.get("clubId", "")),
                "fee":          fee_val,
                "is_loan":      is_loan,
                "mv_at_transfer": mv_val,
                "age_at_transfer": details.get("age"),
            })

        # Sort chronologically
        transfers.sort(key=lambda x: x.get("date") or "")

        # Fee total from API
        fee_sum = th_data.get("data", {}).get("history", {}).get("feeSum", {})
        profile["total_fees_received"] = fee_sum.get("value") if fee_sum else None

    profile["transfers"]   = transfers
    profile["n_transfers"] = len(transfers)

    # Exported: played outside Argentina at some point
    arg_ids = {"2402", "10188", "14836", "61328"}  # Newell's, River, Boca, etc. — fallback by country
    profile["exported"] = any(
        t.get("to_club_id") and t.get("date") and
        # best proxy: if they transferred to a non-AR competition
        t.get("from_club") and t.get("to_club")
        and not (str(t.get("to_club", "")).lower().endswith("ar") or
                 t.get("to_club_id") in arg_ids)
        for t in transfers
        if t.get("to_club")
    )

    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright && playwright install chromium")

    with open(ROSTERS_PATH, encoding="utf-8") as f:
        rosters = json.load(f)

    seen = set()
    players = []
    for agency_data in rosters.values():
        for p in agency_data.get("players", []):
            if p.get("tm_id") and p["tm_id"] not in seen:
                seen.add(p["tm_id"])
                players.append(p)

    print(f"Total jugadores unicos: {len(players)}")

    result = {}
    if OUT_PATH.exists() and args.resume:
        with open(OUT_PATH, encoding="utf-8") as f:
            result = json.load(f)
        print(f"Retomando: {len(result)} ya procesados.")

    pending = [p for p in players if str(p.get("tm_id")) not in result]
    print(f"Pendientes: {len(pending)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=UA, locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        # Warm up session (TM checks referrer/session)
        print("Conectando a Transfermarkt...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        total = len(pending)
        for i, player in enumerate(pending, 1):
            print(f"[{i}/{total}] {player['name']} ({player.get('agency', '')})", end=" ... ")
            profile = fetch_player_profile(page, player)

            if profile:
                result[str(player["tm_id"])] = profile
                n_tr = profile.get("n_transfers", 0)
                mv   = profile.get("market_value")
                fees = profile.get("total_fees_received")
                print(f"OK  transfers={n_tr}  mv={mv}  fees={fees}")
            else:
                print("MISS")
                result[str(player["tm_id"])] = {
                    "tm_id": player["tm_id"], "name": player["name"], "error": True
                }

            if i % 10 == 0 or i == total:
                with open(OUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"  -> guardado ({len(result)} jugadores)")

            time.sleep(0.8 + random.random() * 0.8)

        browser.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ok       = sum(1 for v in result.values() if not v.get("error"))
    exported = sum(1 for v in result.values() if v.get("exported"))
    with_fees = sum(1 for v in result.values() if v.get("total_fees_received"))
    print(f"\nListo. {ok}/{len(result)} jugadores con datos.")
    print(f"Exportados al exterior: {exported}")
    print(f"Con fees registrados: {with_fees}")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
