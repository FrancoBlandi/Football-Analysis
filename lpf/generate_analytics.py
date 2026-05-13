#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LPF Fantasy Analytics — Generador
Apertura 2026 | Análisis probabilístico para Fantasy Manager Argentina
Metodología inspirada en Opta / FPL Review
"""

import json, math, os
from pathlib import Path

JSON_PATH      = r"c:/Users/Franco/DashBoards Futbol/lpf/lpf_data.json"
FORM_PATH      = Path(r"c:/Users/Franco/DashBoards Futbol/lpf/form_data.json")
XGC_PATH       = Path(r"c:/Users/Franco/DashBoards Futbol/lpf/team_xgc.json")
SHOTMAP_PATH   = Path(r"c:/Users/Franco/DashBoards Futbol/lpf/shotmap_xgc.json")
FM_PATH        = Path(r"c:/Users/Franco/DashBoards Futbol/lpf/fm_mapped.json")
FM_PLAYERS_PATH= Path(r"c:/Users/Franco/DashBoards Futbol/lpf/fm_players.json")
OUT_PATH       = r"c:/Users/Franco/DashBoards Futbol/lpf/analytics.html"

# Form weight: 55% recent form / 45% full-season (only applied when form data exists)
FORM_WEIGHT    = 0.55
SEASON_WEIGHT  = 1.0 - FORM_WEIGHT

# Promedio ponderado de pts BPR por aparición: pos1=3, pos2=2, pos3=1 → avg=2
# Se reemplaza por datos exactos por ronda cuando bpr_rounds.json está disponible
BPR_PTS = 2

# ── Ajustes fase eliminatoria (KO) ────────────────────────────────────────
# ESTIMACIÓN — solo aplica a fechas de playoffs con posibilidad de alargue.
# En fase de grupos / temporada regular, estos parámetros no tienen efecto.
#
# En octavos, los GKs proyectados #1-3 tuvieron CS rate << season → corregir P(CS)
PLAYOFF_CS_DISCOUNT  = 0.80   # P(valla invicta) × 0.80 en KO (ambos equipos atacan)
# FDR ventaja/desventaja comprimida: en KO los equipos "débiles" defienden y atacan
# más agresivamente → diferencias de calidad defensiva impactan menos
KO_DEF_MULT_SCALE    = 0.60   # rango def_mult: temporada=±50%, KO=±30%
# Alargue: en KO hay ~20% de probabilidad de prórroga (30 min extra).
# FM da 2 pts fijos por minutos sin importar 90 o 120 min jugados, pero los
# 30 min extra generan oportunidades adicionales de gol/asistencia/BPR.
# Boost = 1 + P(ET) × (30/90) ≈ 1.067 → se aplica a p_goal y p_assist.
KO_ET_PROB           = 0.20   # P(empate al 90') estimada para partidos KO
KO_ET_MULT           = round(1.0 + KO_ET_PROB * (30 / 90), 4)  # ≈ 1.0667

# ── Scoring Fantasy Manager Argentina ─────────────────────────────────────
FM = {
    "goal":         {"G": 8, "D": 8, "M": 5, "F": 4},
    "assist":       3,
    "cs":           {"G": 5, "D": 4, "M": 1, "F": 0},
    "mins":         2,      # jugó >60 min
    "yellow":      -1,
    "red":         -3,
    "winning_goal": 3,      # gol definitivo (el gol de la victoria)
    "save_per_4":   1,      # 1pt cada 4 atajadas (solo GK)
}

# ── Fixtures confirmados Octavos de Final Apertura 2026 ───────────────────
FIXTURES = [
    {"id": 1, "home": "Club Atlético Belgrano",           "away": "Club Atlético Unión de Santa Fe", "round": "Cuartos — Lun 12/5", "date": "Lun 12/5 19:00"},
    {"id": 2, "home": "Argentinos Juniors",               "away": "Huracán",                         "round": "Cuartos — Lun 12/5", "date": "Lun 12/5 21:30"},
    {"id": 3, "home": "Rosario Central",                  "away": "Racing Club",                     "round": "Cuartos — Mar 13/5", "date": "Mar 13/5 19:00"},
    {"id": 4, "home": "River Plate",                      "away": "Gimnasia y Esgrima",              "round": "Cuartos — Mar 13/5", "date": "Mar 13/5 21:30"},
]

# ── DT (entrenador) por equipo — Cuartos de Final 2026 ───────────────────
# Verificar y actualizar antes de cada fecha
COACHES = {
    "Club Atlético Belgrano":           "Ricardo Zielinski",
    "Club Atlético Unión de Santa Fe":  "Leonardo Madelon",
    "Argentinos Juniors":               "Nicolás Diez",
    "Huracán":                          "Diego Hernán Martínez",
    "Rosario Central":                  "Jorge Almirón",
    "Racing Club":                      "Gustavo Costas",
    "River Plate":                      "Eduardo Coudet",
    "Gimnasia y Esgrima":               "Ariel Pereyra",
}

# ── Jugadores no disponibles — Cuartos de Final (12-13 mayo 2026) ──────────
EXCLUDED_PLAYER_IDS = {
    # Lesionados
    1131305,   # Nicolás Palavecino    — Unión de Santa Fe (desgarro muscular)
    1537838,   # Valentín Fascendini   — Unión de Santa Fe (desgarro muscular)
    1094180,   # Ezequiel Cannavo      — Racing Club (desgarro recto anterior)
    790004,    # Paulo Díaz            — River Plate (desgarro recto anterior izq.)
    877299,    # Jaminton Campaz       — Rosario Central (lesión, no estuvo ni en banco en octavos)
    # Suspendidos — roja/doble amarilla en octavos
    579316,    # Lucas Passerini       — Belgrano (doble amarilla vs Talleres)
    792334,    # Eric Ramírez          — Huracán (roja vs Boca)
    943995,    # Fabio Pereyra         — Huracán (doble amarilla vs Boca)
    932234,    # Enzo Martínez         — Gimnasia (roja vs Vélez)
    # Lesionados graves — fuera varios meses (no proyectar)
    1153083,   # Valentín Carboni      — Racing Club (rotura ligamentos cruzados, ~8 meses)
    1807994,   # Nicolás Schelotto     — Gimnasia (5ª amarilla, suspendido para cuartos)
    590036,    # Federico Ricca        — Belgrano (expulsado en octavos vs Talleres)
}

# FM player IDs de lesionados graves sin mapeo SofaScore (excluir del loop de duda)
EXCLUDED_FM_IDS = {
    211190,    # Franco Armani         — River Plate (lesión larga)
}

# ── Override de minutos proyectados — corrige subutilización histórica ────────
# Usar cuando hay info de prensa confirmando titularidad o reemplazo para la fecha.
# El override reemplaza avg_mins_gm en el cálculo de P(titular).
PLAYER_MINUTE_OVERRIDES = {
    # Rosario Central — titulares cuartos vs Racing
    30027:   85,   # Ángel Di María     — titular confirmado
    1116987: 85,   # Alejo Véliz        — titular cuartos (confirmado prensa)
    860045:  85,   # Enzo Copetti       — titular cuartos (confirmado prensa)
    927326:  85,   # Enzo Giménez       — titular confirmado
    # Racing Club — titulares cuartos vs Rosario Central
    1017433: 85,   # Gastón Martirena   — titular confirmado
    46998:   85,   # Marcos Rojo        — titular confirmado
    1201515: 85,   # Baltasar Rodríguez — titular (suspensión levantada)
    # River Plate — Quintero entró como suplente vs San Lorenzo
    221162:  40,   # Juan Fernando Quintero — suplente en octavos
}

# ── Ejecutantes de pelota parada — reducen k de regresión xA (4 en vez de 8) ─
# Rol sistemático: su xA elevado no es ruido, es contribución real de corners/FK
# Agregar/quitar según confirmación; "corners" y/o "freekicks"
SET_PIECE_TAKERS = {
    # Boca Juniors
    "Leandro Paredes":      {"corners", "freekicks"},
    # Unión de Santa Fe
    "Mateo Del Blanco":     {"corners"},
    # Argentinos Juniors
    "Hernán López Muñoz":   {"corners"},
    # Belgrano
    "Lucas Zelarayán":      {"corners", "freekicks"},
    # Rosario Central
    "Ángel Di María":       {"corners", "freekicks"},
    "Jaminton Campaz":      {"corners"},
    # River Plate
    "Marcos Acuña":         {"corners"},
    "Tomás Galván":         {"corners"},
    # CA Independiente
    "Ignacio Malcorra":     {"corners"},
    # Gimnasia y Esgrima
    "Nicolas Schelotto":    {"corners"},
    # Vélez Sarsfield
    "Manuel Lanzini":       {"corners", "freekicks"},
    # Huracán (fuente: minuto a minuto vs Tigre — Cortés ejecutó todos los córners)
    "Oscar Cortés":         {"corners"},
    "Leonardo Gil":         {"freekicks"},
    # Racing Club (Rojas lesionado → Zaracho — fuente: minuto a minuto vs Barracas Central)
    "Matías Zaracho":       {"corners"},
    # CA Talleres (fuente: minuto a minuto vs Riestra y Defensa — Cristaldo ejecutó todos)
    "Franco Cristaldo":     {"corners"},
    # CA Lanús (fuente: minuto a minuto vs Riestra y Central Córdoba — Moreno ejecutó todos)
    "Marcelino Moreno":     {"corners", "freekicks"},
    # Independiente Rivadavia (fuente: minuto a minuto vs Gimnasia Mza — Villa ejecutó ~8 córners)
    "Sebastián Villa":      {"corners"},
    # San Lorenzo (fuente: Copa Sudamericana vs Cuenca — Gulli confirmado)
    "Facundo Gulli":        {"corners"},
    # Estudiantes de La Plata (fuente: minuto a minuto vs Talleres — Cetrá y Neves)
    "Edwuin Cetré":         {"corners"},
    "Gabriel Neves":        {"corners"},
}

# ── Cargar datos ───────────────────────────────────────────────────────────
with open(JSON_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)

# xGC por equipo (expected goals concedidos — reemplaza GC real en FDR)
xgc_data = {}
if XGC_PATH.exists():
    with open(XGC_PATH, encoding="utf-8") as f:
        xgc_data = json.load(f)
    print(f"[xgc] {len(xgc_data)} equipos con datos de xGC cargados")

# Liga avg xGC/pg → base para defensive quality multiplier
_xgc_pgs = [d["xgc_pg"] for d in xgc_data.values() if d.get("xgc_pg")]
LEAGUE_AVG_GC_PG = sum(_xgc_pgs) / len(_xgc_pgs) if _xgc_pgs else 0.82

players_raw = raw["Primera LPF 2026"]

# Forma reciente (últimos 5 partidos, decay 0.75) — opcional; si no existe el archivo se ignora
form_data = {}
if FORM_PATH.exists():
    with open(FORM_PATH, encoding="utf-8") as f:
        form_data = json.load(f)
    _with_form = sum(1 for v in form_data.values() if v.get("form"))
    print(f"[form] {_with_form}/{len(form_data)} jugadores con datos de forma cargados")

# Fantasy Manager AR — datos reales de puntos y BPR (Figura)
fm_data = {}
if FM_PATH.exists():
    with open(FM_PATH, encoding="utf-8") as f:
        fm_data = json.load(f)
    _with_bpr = sum(1 for v in fm_data.values() if (v.get("mvp") or 0) > 0)

# fm_players.json completo — para review de disponibilidad
fm_players_raw = []
if FM_PLAYERS_PATH.exists():
    with open(FM_PLAYERS_PATH, encoding="utf-8") as f:
        fm_players_raw = json.load(f)

# fm_id → sofascore player_id (reverse de fm_mapped)
fm_id_to_ss_id = {int(v["fm_id"]): int(k) for k, v in fm_data.items() if v.get("fm_id")}
print(f"[fm] {len(fm_data)} jugadores cargados ({_with_bpr} con al menos 1 BPR)")

# ss_id → posición FM (para usar scoring correcto: M=5pts gol, F=4pts gol)
_POS_FM_MAP = {"GOALKEEPER": "G", "DEFENDER": "D", "MIDFIELDER": "M", "ATTACKER": "F"}
_fm_id_to_pos = {str(fp["id"]): _POS_FM_MAP.get(fp.get("position", ""), None)
                 for fp in fm_players_raw if fp.get("id")}
ss_id_to_fm_pos = {}
for ss_id, entry in fm_data.items():
    fm_id = entry.get("fm_id")
    if fm_id and str(fm_id) in _fm_id_to_pos and _fm_id_to_pos[str(fm_id)]:
        ss_id_to_fm_pos[int(ss_id)] = _fm_id_to_pos[str(fm_id)]
ss_id_to_fm_pos[1186068] = "M"  # Alan Lescano (ARG) — fix: mapped to L. Lescano (HUR, DEF)

CLUB_SHORT = {
    "Club Atlético Belgrano":           "BEL",
    "Club Atlético Unión de Santa Fe":  "UNI",
    "Argentinos Juniors":               "ARG",
    "Huracán":                          "HUR",
    "Rosario Central":                  "ROS",
    "Racing Club":                      "RAC",
    "River Plate":                      "RIV",
    "Gimnasia y Esgrima":               "GIM",
    "Boca Juniors":                     "BOC",
    "CA Talleres":                      "TAL",
    "CA Lanús":                         "LAN",
    "Independiente Rivadavia":          "IRV",
    "CA Independiente":                 "IND",
    "Estudiantes de La Plata":          "EST",
    "San Lorenzo":                      "SLO",
    "Vélez Sarsfield":                  "VÉL",
}

def club_tag(club_name):
    return CLUB_SHORT.get(club_name) or (club_name or "")[:3].upper()

# ── STEP 1: Stats por equipo ───────────────────────────────────────────────
def get_team_stats(players, xgc_data=None):
    from collections import defaultdict
    clubs = defaultdict(lambda: {"all": [], "gks": [], "xg": 0.0, "goals": 0, "assists": 0})

    for p in players:
        club = p["Club"]
        clubs[club]["all"].append(p)
        if p.get("Posicion") == "G":
            clubs[club]["gks"].append(p)
        clubs[club]["xg"]     += p.get("xG") or 0.0
        clubs[club]["goals"]  += p.get("Goles") or 0
        clubs[club]["assists"]+= p.get("Asistencias") or 0

    result = {}
    for club, d in clubs.items():
        gks = d["gks"]
        if gks:
            main = max(gks, key=lambda g: g.get("Minutos Jugados") or 0)
            gc    = main.get("Goles Recibidos") or 0
            vi    = main.get("Vallas Invictas")  or 0
            games = max(main.get("Partidos Jugados") or 1, 1)
            saves = main.get("Atajadas") or 0
        else:
            gc, vi, games, saves = 14, 4, 14, 28

        g = max(games, 1)
        gc_pg   = gc / g
        vi_rate = vi / g
        xg_pg   = d["xg"] / g
        gf_pg   = d["goals"] / g

        # xGC: usar dato scrapeado si existe, sino fallback a GC real
        xgc_entry = (xgc_data or {}).get(club, {})
        xgc_pg = xgc_entry.get("xgc_pg") or gc_pg

        # Defense score 0–100: usar xGC en lugar de GC real (elimina varianza de arquero)
        gc_norm = max(0.0, min(100.0, 100 - (xgc_pg - 0.4) * 52))
        vi_norm = min(100.0, vi_rate * 130)
        def_score = round(gc_norm * 0.65 + vi_norm * 0.35, 1)

        # Attack score 0–100
        xg_norm  = min(100.0, xg_pg * 42)
        gf_norm  = min(100.0, gf_pg * 33)
        att_score = round(xg_norm * 0.65 + gf_norm * 0.35, 1)

        # FDR 1–5 (desde la perspectiva del atacante)
        fdr = 5 if def_score >= 72 else 4 if def_score >= 56 else 3 if def_score >= 38 else 2 if def_score >= 20 else 1

        result[club] = {
            "games": games, "gc": gc, "vi": vi, "saves": saves,
            "gc_pg":    round(gc_pg, 2),
            "xgc_pg":   round(xgc_pg, 2),
            "vi_pct":   round(vi_rate * 100, 1),
            "xg_pg":    round(xg_pg, 2),
            "gf_pg":    round(gf_pg, 2),
            "def_score": def_score,
            "att_score": att_score,
            "fdr":       fdr,
        }
    return result

team_stats = get_team_stats(players_raw, xgc_data=xgc_data)

# ── Shots on target against por equipo (para xSv de arqueros) ─────────────
# xSv_pg = shots_on_target_against / games * 0.70 (save rate media ~70%)
_sot_vals = []
for club, d in xgc_data.items():
    sot   = d.get("shots_on_target_against") or 0
    games = max(d.get("matches") or 1, 1)
    _sot_vals.append(sot / games)
LEAGUE_AVG_SOT_PG = sum(_sot_vals) / max(len(_sot_vals), 1)

# ── Promedios de posición para regresión a la media ───────────────────────
def compute_positional_averages(players):
    """League-average xG/90 and xA/90 per position (prior for Bayesian shrinkage)."""
    from collections import defaultdict
    totals = defaultdict(lambda: {"xg": 0.0, "xa": 0.0, "mins": 0})
    for p in players:
        pos  = p.get("Posicion")
        mins = p.get("Minutos Jugados") or 0
        if not pos or mins < 90:
            continue
        xg = p.get("xG") or 0.0
        xa = p.get("xA") or 0.0
        if xg == 0:
            xg = ((p.get("Remates al Arco") or 0) + (p.get("Remates Afuera") or 0)) * 0.095
        if xa == 0:
            xa = (p.get("Pases Clave") or 0) * 0.08
        totals[pos]["xg"]   += xg
        totals[pos]["xa"]   += xa
        totals[pos]["mins"] += mins
    avgs = {}
    for pos, d in totals.items():
        m = max(d["mins"], 1)
        avgs[pos] = {"xg_90": round(d["xg"] / m * 90, 4),
                     "xa_90": round(d["xa"] / m * 90, 4)}
    return avgs

def regress_to_mean(xg_90, xa_90, games, pos, pos_avgs, k_xg=8, k_xa=8):
    """Bayesian shrinkage. k=8 → 50/50 at 8 games. Set piece takers use k_xa=4 (trust their xA more)."""
    avg  = pos_avgs.get(pos, {"xg_90": xg_90, "xa_90": xa_90})
    w_xg = games / (games + k_xg)
    w_xa = games / (games + k_xa)
    return (
        round(w_xg * xg_90 + (1 - w_xg) * avg["xg_90"], 4),
        round(w_xa * xa_90 + (1 - w_xa) * avg["xa_90"], 4),
        round(w_xg, 2),
    )

pos_avgs = compute_positional_averages(players_raw)

# Máximo de partidos jugados por equipo → denominador para P(titular)
team_total_games = {}
for _p in players_raw:
    _club = _p.get("Club")
    _gp   = _p.get("Partidos Jugados") or 0
    if _club and _gp > team_total_games.get(_club, 0):
        team_total_games[_club] = _gp

# ── Perfil defensivo por tipo de ataque ───────────────────────────────────
def team_defensive_profiles(players):
    """
    Vulnerability per team: box/wide/aerial (normalized vs. league average).

    Priority:
      1. shotmap_xgc.json — avg xG per goal conceded (real per-shot xG).
         box_vuln  = avg_xg_conceded vs. league avg (high xG → easy goals → box vuln)
         wide_vuln = pct_low_xg vs. league avg      (high % low-xG goals → wide/long-range vuln)
      2. Fallback: GK save locations (Atajadas Dentro/Fuera del Area) — proxy.
    aerial_vuln always comes from GK aerial clearances (no shotmap equivalent).
    """
    from collections import defaultdict

    # ── Aerial vuln from GK data (always) ──
    gk_by_club = defaultdict(list)
    for p in players:
        if p.get("Posicion") == "G":
            gk_by_club[p["Club"]].append(p)

    aerial_by_club = {}
    for club, gks in gk_by_club.items():
        main  = max(gks, key=lambda g: g.get("Minutos Jugados") or 0)
        games = max(main.get("Partidos Jugados") or 1, 1)
        aerial_by_club[club] = (main.get("Salidas Aereas") or 0) / games

    avg_aer = sum(aerial_by_club.values()) / max(len(aerial_by_club), 1)

    # ── Load shotmap data if available ──
    shotmap_data = {}
    if SHOTMAP_PATH.exists():
        with open(SHOTMAP_PATH, encoding="utf-8") as f:
            shotmap_data = json.load(f)
        print(f"[profiles] using shotmap xGC data ({len(shotmap_data)} clubs)")
    else:
        print("[profiles] shotmap_xgc.json not found — falling back to GK save proxy")

    profiles = {}

    if shotmap_data:
        # Build from real per-shot xG data
        league_avg_xg  = next(iter(shotmap_data.values()), {}).get("league_avg_xg", 0.18)
        league_pct_low = next(iter(shotmap_data.values()), {}).get("league_pct_low", 0.20)

        for club, d in shotmap_data.items():
            avg_xg  = d.get("avg_xg_conceded", league_avg_xg)
            pct_low = d.get("pct_low_xg",       league_pct_low)

            # Normalize: deviation / league_avg so values are on same scale
            box_dev  = (avg_xg  - league_avg_xg)  / max(league_avg_xg,  0.01)
            wide_dev = (pct_low - league_pct_low)  / max(league_pct_low, 0.01)
            aer_dev  = (aerial_by_club.get(club, avg_aer) - avg_aer) / max(avg_aer, 0.01)

            top = max([("central", box_dev), ("exterior", wide_dev), ("aéreo", aer_dev)],
                      key=lambda x: x[1])
            profiles[club] = {
                "box_vuln":    round(max(-1.0, min(1.0, box_dev)),  3),
                "wide_vuln":   round(max(-1.0, min(1.0, wide_dev)), 3),
                "aerial_vuln": round(max(-1.0, min(1.0, aer_dev)),  3),
                "vuln_label":  top[0] if top[1] > 0.05 else None,
                "source":      "shotmap",
            }
    else:
        # Fallback: GK save location proxy
        raw = {}
        for club, gks in gk_by_club.items():
            main      = max(gks, key=lambda g: g.get("Minutos Jugados") or 0)
            saves_in  = main.get("Atajadas Dentro del Area") or 0
            saves_out = main.get("Atajadas Fuera del Area")  or 0
            total     = max(saves_in + saves_out, 1)
            raw[club] = {
                "box_ratio":  saves_in / total,
                "wide_ratio": saves_out / total,
                "aerial_pg":  aerial_by_club.get(club, 0),
            }

        avg_box  = sum(v["box_ratio"]  for v in raw.values()) / max(len(raw), 1)
        avg_wide = sum(v["wide_ratio"] for v in raw.values()) / max(len(raw), 1)

        for club, d in raw.items():
            box_dev  = (d["box_ratio"]  - avg_box)  / max(avg_box,  0.01)
            wide_dev = (d["wide_ratio"] - avg_wide) / max(avg_wide, 0.01)
            aer_dev  = (d["aerial_pg"]  - avg_aer)  / max(avg_aer,  0.01)
            top = max([("central", box_dev), ("exterior", wide_dev), ("aéreo", aer_dev)],
                      key=lambda x: x[1])
            profiles[club] = {
                "box_vuln":    round(max(-1.0, min(1.0, box_dev)),  3),
                "wide_vuln":   round(max(-1.0, min(1.0, wide_dev)), 3),
                "aerial_vuln": round(max(-1.0, min(1.0, aer_dev)),  3),
                "vuln_label":  top[0] if top[1] > 0.05 else None,
                "source":      "gk_proxy",
            }

    return profiles

def classify_player_type(p, xg_90, xa_90):
    pos   = p.get("Posicion")
    mins  = max(p.get("Minutos Jugados") or 1, 1)
    shots = (p.get("Remates al Arco") or 0) + (p.get("Remates Afuera") or 0)
    kp    = p.get("Pases Clave") or 0
    sh90  = shots / mins * 90
    kp90  = kp    / mins * 90

    if pos == "F":
        # wide_fwd primero: crea más de lo que dispara (extremo, enganche por afuera)
        if xa_90 >= 0.14 and sh90 < 2.2:
            return "wide_fwd"
        # box_striker: alto volumen de tiros, casi sin asistencias — 9 de área puro
        if sh90 >= 2.0 and xa_90 < 0.10:
            return "box_striker"
        # complete_striker: dispara bastante Y crea — 9 completo
        if sh90 >= 1.7 and xa_90 >= 0.10:
            return "complete_striker"
        # poacher: pocas chances pero de alta calidad (xG/90 alto sin volumen)
        if xg_90 >= 0.25 and sh90 < 1.5:
            return "poacher"
        return "pressing_fwd"

    elif pos == "M":
        # shadow_striker: dispara mucho y con alto xG — mediocampista goleador
        if sh90 >= 2.0 and xg_90 >= 0.20:
            return "shadow_striker"
        # playmaker puro: xA muy alto, creador principal
        if xa_90 >= 0.22:
            return "playmaker"
        # attacking_mid: amenaza tanto en gol como en asistencia
        if xg_90 >= 0.10 and xa_90 >= 0.10:
            return "attacking_mid"
        # creative_mid: creador sin ser puro playmaker — enganche, media punta creadora
        if xa_90 >= 0.13 and kp90 >= 1.3:
            return "creative_mid"
        # goalscoring_mid: llegador, se proyecta al gol
        if xg_90 >= 0.12:
            return "goalscoring_mid"
        # cdm: volante de contención, bajo output ofensivo
        if xg_90 < 0.05 and xa_90 < 0.07:
            return "cdm"
        return "box_to_box"

    elif pos == "D":
        # overlapping_def: carrilero/lateral muy ofensivo
        if xa_90 >= 0.12 or (kp90 >= 1.8 and xa_90 >= 0.07):
            return "overlapping_def"
        # attacking_def: se proyecta al ataque aunque no es carrilero puro
        if xa_90 >= 0.07 or xg_90 >= 0.10:
            return "attacking_def"
        return "defender"

    return "other"


def get_type_mult(player_type, opp_profile):
    """Returns (goal_mult, assist_mult) ±10% max based on player style vs. opponent's defensive weakness."""
    bv = opp_profile.get("box_vuln",  0.0)
    wv = opp_profile.get("wide_vuln", 0.0)
    # (goal_adj, assist_adj): cuánto de bv/wv se traslada al multiplicador
    weights = {
        # Forwards
        "box_striker":      (bv * 0.14, bv * 0.02),   # vive en el área, casi nada wide
        "complete_striker": (bv * 0.10, wv * 0.06),   # box + algo wide en asistencias
        "wide_fwd":         (wv * 0.05, wv * 0.13),   # extremo: amenaza por afuera
        "poacher":          (bv * 0.11, bv * 0.01),   # oportunista central
        "pressing_fwd":     (bv * 0.05, wv * 0.04),   # genérico, bajo impacto
        # Mediocampistas
        "shadow_striker":   (bv * 0.13, bv * 0.04),   # enganche goleador, central
        "playmaker":        (wv * 0.03, wv * 0.13),   # conductor, amenaza wide
        "attacking_mid":    (bv * 0.08, bv * 0.07),   # ambas dimensiones centrales
        "creative_mid":     (wv * 0.03, wv * 0.09),   # creador mixto
        "goalscoring_mid":  (bv * 0.11, bv * 0.02),   # llegador, central
        "cdm":              (bv * 0.01, wv * 0.01),   # mínimo impacto ofensivo
        "box_to_box":       (bv * 0.05, bv * 0.04),   # equilibrado
        # Defensores
        "overlapping_def":  (bv * 0.01, wv * 0.10),   # carrilero, amenaza wide
        "attacking_def":    (bv * 0.03, wv * 0.06),   # llegador mixto
        "defender":         (0.0,       0.0),
        "other":            (0.0,       0.0),
    }
    adj = weights.get(player_type, (0.0, 0.0))
    return (
        round(max(0.90, min(1.10, 1.0 + adj[0])), 3),
        round(max(0.90, min(1.10, 1.0 + adj[1])), 3),
    )


def compute_consistency(form_matches):
    """
    Coeficiente de variación del output combinado (xG+xA)/90 en los últimos partidos.
    Devuelve 0–100: 100 = perfectamente consistente, 0 = boom-or-bust extremo.
    """
    active = [m for m in form_matches if (m.get("mins") or 0) >= 20]
    if len(active) < 2:
        return None
    outputs = [(m["xg"] + m["xa"]) / m["mins"] * 90 for m in active]
    mean = sum(outputs) / len(active)
    if mean < 0.02:
        return 50   # jugador de muy bajo output — neutral
    variance = sum((x - mean) ** 2 for x in outputs) / len(active)
    cv = (variance ** 0.5) / mean          # coeficiente de variación
    return max(0, min(100, round(100 - cv * 50)))

def_profiles = team_defensive_profiles(players_raw)

# ── STEP 2: Proyección por jugador dado un fixture ─────────────────────────
def project_player(p, opp_club, is_home, ts):
    pos   = p.get("Posicion")
    mins  = p.get("Minutos Jugados") or 0
    games = max(p.get("Partidos Jugados") or 1, 1)

    if mins < 90 or not pos:
        return None

    # xG y xA totales (fallback a shots si no hay xG)
    xg_tot = p.get("xG") or 0.0
    xa_tot = p.get("xA") or 0.0
    if xg_tot == 0:
        shots  = (p.get("Remates al Arco") or 0) + (p.get("Remates Afuera") or 0)
        xg_tot = shots * 0.095   # conversión media LPF
    if xa_tot == 0:
        kp     = p.get("Pases Clave") or 0
        xa_tot = kp * 0.08

    xg_90 = (xg_tot / mins * 90) if mins > 0 else 0.0
    xa_90 = (xa_tot / mins * 90) if mins > 0 else 0.0

    # Blend with recent form data (last 5 LPF matches, exponential decay)
    pid_str    = str(p.get("player_id", ""))
    form_entry = form_data.get(pid_str, {}).get("form") if pid_str else None
    has_form   = bool(form_entry)
    if has_form:
        # Cap form values — un partido raro (pocos min + gol) no debe explotar el blend
        POS_XG_CAP = {"G": 0.20, "D": 0.50, "M": 0.70, "F": 1.10}
        form_xg = min(form_entry["form_xg_90"], POS_XG_CAP.get(pos, 0.80))
        form_xa = min(form_entry["form_xa_90"], 0.80)
        xg_90 = SEASON_WEIGHT * xg_90 + FORM_WEIGHT * form_xg
        xa_90 = SEASON_WEIGHT * xa_90 + FORM_WEIGHT * form_xa

    # xGI/90 (xG + xA combinados, post-blend)
    xgi_90_val = round(xg_90 + xa_90, 3)

    # ── Métricas de creación (season, per 90) ──────────────────────────────
    kp      = p.get("Pases Clave") or 0
    gc_cr   = p.get("Grandes Chances Creadas") or 0
    goals_r = p.get("Goles") or 0
    assists_r = p.get("Asistencias") or 0
    dribbles = p.get("Regates Exitosos") or 0

    sca_90_val         = round((kp + goals_r + assists_r) / mins * 90, 2) if mins > 0 else 0.0
    gca_90_val         = round((gc_cr + goals_r + assists_r) / mins * 90, 2) if mins > 0 else 0.0
    prog_carries_90_val = round(dribbles / mins * 90, 2) if mins > 0 else 0.0

    # ── P(titular): probabilidad de jugar >60 min ──────────────────────────
    # Metodología FPL Review: separar rotation risk de injury risk por posición.
    # GK/D: ausencias históricas son mayormente lesiones (no predice el próximo partido).
    #       → disponibilidad "blanda": base alta + pequeño ajuste por historial.
    # M/F: ausencias incluyen rotación táctica (SÍ predice) → disponibilidad lineal.
    team_games  = max(team_total_games.get(p.get("Club",""), games), games)
    availability = min(1.0, games / team_games)
    avg_mins_gm  = mins / games

    # Override manual de minutos proyectados (titularidades confirmadas por prensa)
    pid_int = p.get("player_id")
    historical_avg_m = avg_mins_gm   # guardar antes del override para role-change check
    if pid_int in PLAYER_MINUTE_OVERRIDES:
        avg_mins_gm  = PLAYER_MINUTE_OVERRIDES[pid_int]
        # Descuento por cambio de rol: suplente habitual proyectado como titular.
        # xG/90 de sub sobreestima el rendimiento de 85+ min (entradas en momentos
        # ventajosos: juego abierto, rival cansado). Descuento ~20% cuando el
        # promedio histórico < 55 min/PJ y el override lo proyecta como titular (≥70 min).
        if historical_avg_m < 55 and avg_mins_gm >= 70:
            xg_90 *= 0.80
            xa_90 *= 0.80
            _role_change_log.append(
                f"  [role-change] {p.get('Jugador')} ({p.get('Club')}) - "
                f"hist {historical_avg_m:.0f}min/PJ -> override {avg_mins_gm:.0f}min: xG/90 x0.80"
            )
        availability = 1.0 if avg_mins_gm >= 60 else availability

    if pos == "G":
        p_over60 = 0.96                                            # no existe el cambio de arquero
    elif pos == "D":
        p_over60 = min(0.94, max(0.10, (avg_mins_gm - 10) / 70)) # raramente salen antes del 60'
    elif pos == "M":
        p_over60 = min(0.92, max(0.05, (avg_mins_gm - 20) / 65))
    else:                                                          # F
        p_over60 = min(0.90, max(0.05, (avg_mins_gm - 25) / 60))
    p_play_val = round(availability * p_over60, 2)

    # Consistencia + rating reciente: últimos 5 partidos del Apertura 2026
    form_matches  = form_data.get(pid_str, {}).get("matches", []) if pid_str else []
    consistency   = compute_consistency(form_matches)
    rated = [m["rating"] for m in form_matches if (m.get("mins") or 0) >= 20 and m.get("rating") is not None]
    form_rating   = round(sum(rated) / len(rated), 2) if rated else None

    # Set piece taker: reducir k_xa → confiar más en su xA observado
    sp_role      = SET_PIECE_TAKERS.get(p.get("Jugador", ""), set())
    is_sp_taker  = bool(sp_role)
    k_xa         = 4 if is_sp_taker else 8

    # Penalty taker: separar xG de penales del open-play antes de regresar
    # El rol de ejecutante no es ruido — no lo regresamos hacia la media
    pen_goals    = p.get("Goles de Penal") or 0
    is_pen_taker = pen_goals > 0 and pos != "G"
    if is_pen_taker:
        pen_xg_90 = (pen_goals / 0.78 * 0.76) / (mins / 90)
        op_xg_90  = max(0.0, xg_90 - pen_xg_90)
        op_reg, xa_90_reg, reg_w = regress_to_mean(op_xg_90, xa_90, games, pos, pos_avgs, k_xa=k_xa)
        xg_90_reg = op_reg + pen_xg_90
    else:
        xg_90_reg, xa_90_reg, reg_w = regress_to_mean(xg_90, xa_90, games, pos, pos_avgs, k_xa=k_xa)

    # npxG/90 — xG sin penales (season, pre-blend)
    pen_xg_tot  = (pen_goals / 0.78 * 0.76) if is_pen_taker else 0.0
    npxg_90_val = round(max(0.0, xg_tot - pen_xg_tot) / mins * 90, 3) if mins > 0 else 0.0

    opp  = ts.get(opp_club, {"def_score": 50, "att_score": 50, "fdr": 3})
    own  = ts.get(p["Club"],   {"def_score": 50, "att_score": 50})

    opp_def = opp["def_score"]

    # Multiplicadores — rango comprimido en fases KO (KO_DEF_MULT_SCALE)
    def_mult  = 1.0 + (50 - opp_def) / 100 * KO_DEF_MULT_SCALE   # KO: ±30%
    home_mult = 1.12 if is_home else 0.88
    if avg_mins_gm >= 60:
        role, exp_mins = "Titular",    82
    elif avg_mins_gm >= 35:
        role, exp_mins = "Rotacional", 55
    else:
        role, exp_mins = "Suplente",   25
    mins_fac = exp_mins / 90

    # Perfil de ataque del jugador vs. vulnerabilidad defensiva del rival
    player_type         = classify_player_type(p, xg_90, xa_90)
    opp_prof            = def_profiles.get(opp_club, {})
    g_type_m, a_type_m  = get_type_mult(player_type, opp_prof)

    # Multiplicadores por posición (calibrados para p_goal razonable)
    GOAL_POS   = {"G": 0.004, "D": 0.055, "M": 0.44, "F": 0.85}
    ASSIST_POS = {"G": 0.004, "D": 0.11,  "M": 0.60, "F": 0.38}

    p_goal   = min(0.70, xg_90_reg * def_mult * home_mult * GOAL_POS.get(pos, 0.3) * mins_fac * g_type_m * KO_ET_MULT)
    p_assist = min(0.55, xa_90_reg * def_mult * home_mult * ASSIST_POS.get(pos, 0.3) * mins_fac * a_type_m * KO_ET_MULT)

    # Clean sheet — modelo Poisson (alineado con Opta)
    # P(VI=0) = e^(-λ) donde λ = blend xGA propio + xGF rival, ajustado por local/visita
    # xGA propio: blend 60% xgc_pg (estructura defensiva) + 40% gc_pg real (incluye calidad del arquero)
    own_xgc_pg  = own.get("xgc_pg") or LEAGUE_AVG_GC_PG
    own_gc_pg   = own.get("gc_pg")  or LEAGUE_AVG_GC_PG
    own_def_pg  = own_xgc_pg * 0.60 + own_gc_pg * 0.40
    opp_xgf_pg  = opp.get("xg_pg") or LEAGUE_AVG_GC_PG
    lam         = (own_def_pg * 0.55 + opp_xgf_pg * 0.45) * (0.85 if is_home else 1.15)
    p_cs        = min(0.60, max(0.03, math.exp(-lam))) * PLAYOFF_CS_DISCOUNT

    # xSv: para arqueros — expected saves/pg (solo para display, no modifica p_cs)
    # p_cs ya incorpora xgc_pg que correlaciona con SOT → no double-count
    xSv_pg = 0.0
    if pos == "G":
        club_xgc  = xgc_data.get(p.get("Club", ""), {})
        sot       = club_xgc.get("shots_on_target_against") or 0
        gm        = max(club_xgc.get("matches") or 1, 1)
        sot_pg    = sot / gm
        xSv_pg    = round(sot_pg * 0.70, 2)

    # xPts Fantasy Manager
    yellows  = p.get("Amarillas") or 0
    card_pen = (yellows / games) * FM["yellow"]

    # Gol definitivo (+3 pts) — gol que da la victoria final
    # E[gol_def] = p_goal × P(partido ganado por 1 gol) / λ_equipo
    # λ_equipo: expected goals del equipo vs este rival/localía
    own_att_pg = (own.get("xg_pg", LEAGUE_AVG_GC_PG) * 0.65 +
                  own.get("gf_pg", LEAGUE_AVG_GC_PG) * 0.35)
    λ_scored   = own_att_pg * (opp.get("xgc_pg", LEAGUE_AVG_GC_PG) /
                               max(LEAGUE_AVG_GC_PG, 0.01)) * (1.15 if is_home else 0.85)
    # ~28% de partidos LPF se ganan por exactamente 1 gol de diferencia
    gol_def_pts = p_goal * 0.28 / max(λ_scored, 0.5) * FM["winning_goal"]

    # Atajadas (+1pt cada 4) — solo GK, usando xSv_pg calculado arriba
    save_pts = (xSv_pg / 4.0) * mins_fac if pos == "G" else 0.0

    xpts = (
        p_goal      * FM["goal"].get(pos, 4) +
        p_assist    * FM["assist"] +
        p_cs        * FM["cs"].get(pos, 0) +
        mins_fac    * FM["mins"] +
        card_pen    +
        gol_def_pts +
        save_pts
    )

    # Consistencia: jugadores boom-or-bust bajan hasta 8% en xPts
    cons_mult = (0.94 + 0.12 * consistency / 100) if consistency is not None else 1.0
    xpts      = xpts * cons_mult

    # Disponibilidad: P(juega) × E[pts|juega] = xPts real (metodología Opta)
    xpts = xpts * availability

    # BPR (Bonus por Rendimiento / Figura) — Fantasy Manager AR
    # Sumamos E[BPR pts] = tasa histórica de MVP × BPR_PTS × disponibilidad
    # Fuente: fm_mapped.json scrapeado de fantasymanager.ar
    pid_str_fm  = str(p.get("player_id", ""))
    fm_entry    = fm_data.get(pid_str_fm, {})
    fm_mean_pts = fm_entry.get("mean_points")
    fm_price    = fm_entry.get("price")         # precio en FM (millones)
    fm_mvp_raw  = fm_entry.get("mvp") or 0
    bpr_rate    = fm_mvp_raw / games             # fracción de fechas con BPR
    # E[pts por BPR] = tasa × avg_pts. Jugadores con tasa alta tienden a BPR1 (3pts),
    # los de tasa baja a BPR3 (1pt). Interpolamos linealmente entre 1 y 3.
    bpr_avg_pts = 1.0 + min(bpr_rate, 0.30) / 0.30 * 2.0  # 1pt a tasa=0, 3pts a tasa≥30%
    bpr_boost   = bpr_rate * bpr_avg_pts * availability
    xpts        = round(xpts + bpr_boost, 2)

    # Captaincy score: xPts (ya con BPR) × consistencia × techo de posición
    CAP_POS_MULT = {"G": 0.70, "D": 0.88, "M": 1.00, "F": 1.08}
    cap_score = round(xpts * (0.5 + 0.5 * (consistency or 50) / 100) * CAP_POS_MULT.get(pos, 1.0), 2)

    # xG overperformance: goles reales vs xG acumulado (solo con xG real de SofaScore)
    has_real_xg = (p.get("xG") or 0) > 0
    xg_over     = round((p.get("Goles") or 0) - (p.get("xG") or 0), 2) if has_real_xg else None

    goal_pts_val = FM["goal"].get(pos, 4)
    cs_pts_val   = FM["cs"].get(pos, 0)
    breakdown = {
        "gol":     round(p_goal      * goal_pts_val, 2),
        "asist":   round(p_assist    * FM["assist"],  2),
        "vi":      round(p_cs        * cs_pts_val,    2),
        "mins":    round(mins_fac    * FM["mins"],    2),
        "cards":   round(card_pen,   2),
        "gol_def": round(gol_def_pts, 2),
        "saves":   round(save_pts,    2),
    }

    return {
        "p_goal":      round(p_goal   * 100, 1),
        "p_assist":    round(p_assist * 100, 1),
        "p_cs":        round(p_cs     * 100, 1),
        "xg_90":       round(xg_90, 3),
        "xa_90":       round(xa_90, 3),
        "xg_90_reg":   round(xg_90_reg, 3),
        "xa_90_reg":   round(xa_90_reg, 3),
        "fdr_opp":     opp["fdr"],
        "xpts":        round(xpts, 2),
        "mins_fac":    round(mins_fac, 2),
        "role":         role,
        "player_type":  player_type,
        "g_type_m":     g_type_m,
        "a_type_m":     a_type_m,
        "reg_w":        reg_w,
        "is_pen_taker": is_pen_taker,
        "is_sp_taker":  is_sp_taker,
        "sp_role":      list(sp_role),
        "has_form":     has_form,
        "consistency":  consistency,
        "form_rating":  form_rating,
        "npxg_90":      npxg_90_val,
        "xgi_90":       xgi_90_val,
        "xg_over":      xg_over,
        "cap_score":    cap_score,
        "sca_90":       sca_90_val,
        "gca_90":       gca_90_val,
        "prog_carries_90": prog_carries_90_val,
        "p_play":       p_play_val,
        "xSv_pg":       xSv_pg,
        "breakdown":    breakdown,
        "fm_mean_pts":  fm_mean_pts,
        "fm_mvp":       fm_mvp_raw,
        "bpr_rate":     round(bpr_rate * 100, 1),
        "fm_price":     fm_price,
        "xpts_per_m":   round(xpts / fm_price, 2) if fm_price and fm_price > 0 else None,
        "style_match":  round({
            # (peso_gol, peso_asist) para combinar los dos multiplicadores en un solo número
            "box_striker":      (1.00, 0.00),
            "complete_striker": (0.65, 0.35),
            "wide_fwd":         (0.15, 0.85),
            "poacher":          (0.90, 0.10),
            "pressing_fwd":     (0.60, 0.40),
            "shadow_striker":   (0.75, 0.25),
            "playmaker":        (0.15, 0.85),
            "attacking_mid":    (0.50, 0.50),
            "creative_mid":     (0.25, 0.75),
            "goalscoring_mid":  (0.85, 0.15),
            "cdm":              (0.50, 0.50),
            "box_to_box":       (0.55, 0.45),
            "overlapping_def":  (0.10, 0.90),
            "attacking_def":    (0.40, 0.60),
            "defender":         (0.00, 0.00),
            "other":            (0.00, 0.00),
        }.get(player_type, (0.5, 0.5))[0] * (g_type_m - 1) * 100 +
        {
            "box_striker":      (1.00, 0.00),
            "complete_striker": (0.65, 0.35),
            "wide_fwd":         (0.15, 0.85),
            "poacher":          (0.90, 0.10),
            "pressing_fwd":     (0.60, 0.40),
            "shadow_striker":   (0.75, 0.25),
            "playmaker":        (0.15, 0.85),
            "attacking_mid":    (0.50, 0.50),
            "creative_mid":     (0.25, 0.75),
            "goalscoring_mid":  (0.85, 0.15),
            "cdm":              (0.50, 0.50),
            "box_to_box":       (0.55, 0.45),
            "overlapping_def":  (0.10, 0.90),
            "attacking_def":    (0.40, 0.60),
            "defender":         (0.00, 0.00),
            "other":            (0.00, 0.00),
        }.get(player_type, (0.5, 0.5))[1] * (a_type_m - 1) * 100, 1),
    }

# ── STEP 3: Armar dataset de jugadores ────────────────────────────────────
fixture_map = {}   # club → (rival, is_home)
for fx in FIXTURES:
    fixture_map[fx["home"]] = (fx["away"], True)
    fixture_map[fx["away"]] = (fx["home"], False)

# Pre-computar el arquero titular de cada equipo (más minutos, excluyendo no disponibles)
gk_starter = {}
for p in players_raw:
    if p.get("Posicion") == "G" and p.get("player_id") not in EXCLUDED_PLAYER_IDS:
        club = p.get("Club")
        mins = p.get("Minutos Jugados") or 0
        if club not in gk_starter or mins > (gk_starter[club].get("Minutos Jugados") or 0):
            gk_starter[club] = p

player_list = []
_role_change_log = []
for p in players_raw:
    club = p.get("Club")
    pos  = p.get("Posicion")
    mins = p.get("Minutos Jugados") or 0
    if mins < 90 or not pos or club not in fixture_map:
        continue
    if p.get("player_id") in EXCLUDED_PLAYER_IDS:
        continue
    # Para arqueros, solo incluir el titular
    if pos == "G" and gk_starter.get(club, {}).get("player_id") != p.get("player_id"):
        continue

    # Usar posición de FM cuando existe (más relevante para scoring de fantasy)
    fm_pos = ss_id_to_fm_pos.get(p.get("player_id"))
    if fm_pos and fm_pos != pos:
        p = {**p, "Posicion": fm_pos}
        pos = fm_pos

    opp_club, is_home = fixture_map[club]
    proj = project_player(p, opp_club, is_home, team_stats)
    if proj is None:
        continue

    opp_ts = team_stats.get(opp_club, {})
    player_list.append({
        "name":        p["Jugador"],
        "club":        club,
        "opp":         opp_club,
        "pos":         pos,
        "is_home":     is_home,
        "age":         p.get("Edad"),
        "country":     p.get("Pais"),
        "games":       p.get("Partidos Jugados") or 0,
        "mins":        mins,
        "goals":       p.get("Goles") or 0,
        "assists":     p.get("Asistencias") or 0,
        "rating":      p.get("Rating"),
        "xg":          round(p.get("xG") or 0, 2),
        "xa":          round(p.get("xA") or 0, 2),
        "key_passes":  p.get("Pases Clave") or 0,
        "big_chances": p.get("Grandes Chances Creadas") or 0,
        "shots":       (p.get("Remates al Arco") or 0) + (p.get("Remates Afuera") or 0),
        "amarillas":   p.get("Amarillas") or 0,
        "fdr_opp":     opp_ts.get("fdr", 3),
        "role":         proj.get("role", "Titular"),
        "player_type":  proj.get("player_type", "other"),
        "is_pen_taker": proj.get("is_pen_taker", False),
        "is_sp_taker":  proj.get("is_sp_taker",  False),
        "sp_role":      proj.get("sp_role", []),
        **proj,
    })

player_list.sort(key=lambda x: x["xpts"], reverse=True)

# ── STEP 4: Dataset para el simulador (todos los jugadores con mins ≥ 90) ──
sim_players = []
for p in players_raw:
    pos  = p.get("Posicion")
    mins = p.get("Minutos Jugados") or 0
    games= max(p.get("Partidos Jugados") or 1, 1)
    if mins < 90 or not pos:
        continue
    if p.get("player_id") in EXCLUDED_PLAYER_IDS:
        continue

    xg_tot = p.get("xG") or 0.0
    xa_tot = p.get("xA") or 0.0
    if xg_tot == 0:
        shots  = (p.get("Remates al Arco") or 0) + (p.get("Remates Afuera") or 0)
        xg_tot = shots * 0.095
    if xa_tot == 0:
        kp     = p.get("Pases Clave") or 0
        xa_tot = kp * 0.08

    xg_90 = (xg_tot / mins * 90) if mins > 0 else 0.0
    xa_90 = (xa_tot / mins * 90) if mins > 0 else 0.0
    xg_90_reg, xa_90_reg, _ = regress_to_mean(xg_90, xa_90, games, pos, pos_avgs)

    avg_m   = PLAYER_MINUTE_OVERRIDES.get(p.get("player_id"), mins / games)
    sim_emins = 82 if avg_m >= 60 else 55 if avg_m >= 35 else 25
    sim_role  = "Titular" if avg_m >= 60 else "Rotacional" if avg_m >= 35 else "Suplente"
    sim_players.append({
        "name":        p["Jugador"],
        "club":        p["Club"],
        "pos":         pos,
        "mins_fac":    round(sim_emins / 90, 2),
        "role":        sim_role,
        "xg_90":       round(xg_90, 4),
        "xa_90":       round(xa_90, 4),
        "xg_90_reg":   round(xg_90_reg, 4),
        "xa_90_reg":   round(xa_90_reg, 4),
        "goals":       p.get("Goles") or 0,
        "assists":     p.get("Asistencias") or 0,
        "rating":      p.get("Rating"),
        "amarillas":   p.get("Amarillas") or 0,
        "games":       games,
    })

# ── STEP 5: Ordenar FDR Table ──────────────────────────────────────────────
fdr_table = sorted(
    [{"club": c, **v} for c, v in team_stats.items()],
    key=lambda x: x["def_score"],
    reverse=True
)

# Agregar jugadores con duda de disponibilidad al player_list antes de serializar
# (la función se define más abajo pero se llama aquí para que queden en DATA)
def _add_doubt_early():
    from collections import defaultdict as _dd
    FIXTURE_CLUBS = {f["home"] for f in FIXTURES} | {f["away"] for f in FIXTURES}
    fixture_map   = {f["home"]: (f["away"], True)  for f in FIXTURES}
    fixture_map  |= {f["away"]: (f["home"], False) for f in FIXTURES}
    in_analytics_names = {pl["name"].lower() for pl in player_list}
    ss_by_id = {p["player_id"]: p for p in players_raw}
    POS_FM_TO_SS = {"GOALKEEPER": "G", "DEFENDER": "D", "MIDFIELDER": "M", "ATTACKER": "F"}
    added = 0
    for fp in fm_players_raw:
        status = fp.get("status", "")
        if status not in ("injured", "suspended"): continue
        team  = fp.get("team", {}).get("name", "")
        if team not in FIXTURE_CLUBS: continue
        price = fp.get("price") or 0
        if price <= 0: continue
        name  = fp.get("full_name") or fp.get("name", "")
        fm_id = fp["id"]
        if fm_id in EXCLUDED_FM_IDS: continue          # lesión larga confirmada (sin ss_id)
        if name.lower() in in_analytics_names: continue
        ss_id = fm_id_to_ss_id.get(fm_id)
        if ss_id and ss_id in EXCLUDED_PLAYER_IDS: continue  # lesión larga con ss_id
        lp    = ss_by_id.get(ss_id, {}) if ss_id else {}
        opp_club, is_home = fixture_map.get(team, ("?", True))
        fdr_opp = team_stats.get(opp_club, {}).get("fdr", 3)
        pos      = POS_FM_TO_SS.get(fp.get("position", ""), "M")
        mean_pts = fp.get("mean_points") or 0
        player_list.append({
            "name": name, "club": team, "opp": opp_club, "pos": pos,
            "is_home": is_home, "age": fp.get("age") or 0, "country": "",
            "games": 0, "mins": lp.get("Minutos Jugados") or 0,
            "goals": fp.get("goals") or 0, "assists": fp.get("assists") or 0,
            "rating": fp.get("rating") or 0,
            "xg": 0, "xa": 0, "key_passes": 0,
            "xg_90": 0.0, "xa_90": 0.0, "xgi_90": 0.0,
            "npxg_90": None, "sca_90": None, "gca_90": None,
            "prog_carries_90": None, "xg_over": None,
            "p_goal": 0.0, "p_assist": 0.0, "p_cs": 0.0, "p_play": 0.0,
            "xpts": 0.0,       # xpts=0 hasta confirmar disponibilidad
            "xpts_per_m": None,
            "consistency": None, "cap_score": 0.0, "role": "Duda",
            "fdr_opp": fdr_opp, "fm_price": price, "fm_mean_pts": mean_pts,
            "bpr_rate": 0.0, "xSv_pg": 0.0,
            "has_form": False, "is_pen_taker": False, "is_sp_taker": False,
            "sp_role": [], "player_type": "", "style_match": None,
            "player_id": ss_id or 0,
            "doubt": True, "doubt_status": status,
        })
        added += 1
    print(f"[doubt] {added} jugadores de duda agregados")

_add_doubt_early()

# ── Serializar datos para el HTML ─────────────────────────────────────────
DATA = {
    "fixtures":    FIXTURES,
    "players":     player_list,
    "team_stats":  team_stats,
    "fdr_table":   fdr_table,
    "sim_players": sim_players,
    "all_clubs":   sorted(team_stats.keys()),
    "fm_scoring":  FM,
    "def_profiles": def_profiles,
    "pos_avgs":     pos_avgs,
}

data_json = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))

def build_leaders_html(players, n=3):
    """Generate the horizontal leaders bar HTML showing top-N per category."""
    cats = [
        ("xpts",       "xPts",      "lc-xpts", lambda p: p.get("xpts") or 0,         lambda v: f"{v:.2f}"),
        ("xg_90",      "xG/90",     "lc-xg",   lambda p: p.get("xg_90") or 0,        lambda v: f"{v:.3f}"),
        ("xa_90",      "xA/90",     "lc-xa",   lambda p: p.get("xa_90") or 0,        lambda v: f"{v:.3f}"),
        ("p_cs",       "P(VI)",     "lc-pvi",  lambda p: p.get("p_cs") or 0,         lambda v: f"{v:.0f}%"),
        ("xpts_per_m", "xPts/M$",  "lc-val",  lambda p: p.get("xpts_per_m") or 0,   lambda v: f"{v:.2f}"),
        ("cap_score",  "Cap Score", "lc-best", lambda p: p.get("cap_score") or 0,    lambda v: f"{v:.2f}"),
    ]
    parts = []
    for key, label, cls, sorter, fmt in cats:
        ranked = sorted([p for p in players if sorter(p) > 0], key=sorter, reverse=True)[:n]
        rows_html = ""
        for i, p in enumerate(ranked, 1):
            val = sorter(p)
            club_short = club_tag(p.get("club") or "")
            rows_html += (
                f'<div class="leader-row">'
                f'<span class="leader-rank">{i}</span>'
                f'<div class="leader-info">'
                f'<div class="leader-name">{p["name"]}</div>'
                f'<div class="leader-club-tag">{club_short}</div>'
                f'</div>'
                f'<span class="leader-val">{fmt(val)}</span>'
                f'</div>'
            )
        parts.append(
            f'<div class="leader-card {cls}">'
            f'<div class="leader-cat">{label}</div>'
            f'{rows_html}'
            f'</div>'
        )
    return "".join(parts)

leaders_html = build_leaders_html(player_list)

def build_captain_card_html(players, n=3):
    """Prominent captain recommendation card — top N by cap_score."""
    ranked = sorted(
        [p for p in players if (p.get("cap_score") or 0) > 0 and (p.get("fm_price") or 0) > 0],
        key=lambda p: p.get("cap_score") or 0, reverse=True
    )[:n]

    POS_COLORS = {"G": "#7c3aed", "D": "#059669", "M": "#1d4ed8", "F": "#ea580c"}
    POS_LABELS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
    FDR_COLORS = {"1": "#00c853", "2": "#69f0ae", "3": "#f59e0b", "4": "#f97316", "5": "#ef4444"}

    rows = ""
    for rank, p in enumerate(ranked, 1):
        pos       = (p.get("pos") or "M").upper()
        pc        = POS_COLORS.get(pos, "#64748b")
        pl        = POS_LABELS.get(pos, pos)
        fdr       = str(p.get("fdr_opp") or 3)
        fdr_col   = FDR_COLORS.get(fdr, "#f59e0b")
        opp_short = club_tag(p.get("opp") or "")
        cons      = p.get("consistency")
        cons_str  = f"{cons}/100" if cons is not None else "—"
        xpts      = p.get("xpts") or 0
        cap_s     = p.get("cap_score") or 0
        name      = p.get("name", "")
        club      = p.get("club", "")
        price     = p.get("fm_price") or 0

        medal = ["🥇", "🥈", "🥉"][rank - 1]
        is_top = ' style="background:#fffbeb;border:1.5px solid #fbbf24;"' if rank == 1 else ""

        rows += f"""
        <div class="cap-row"{is_top}>
          <div class="cap-rank">{medal}</div>
          <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;">
            <div class="cap-avatar" style="background:{pc};">{pl}</div>
            <div style="min-width:0;">
              <div class="cap-name">{name}</div>
              <div class="cap-club">{club}</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:12px;flex-shrink:0;">
            <div style="text-align:center;">
              <div class="cap-stat-label">Cap Score</div>
              <div class="cap-stat-val" style="color:#1a56db;">{cap_s:.2f}</div>
            </div>
            <div style="text-align:center;">
              <div class="cap-stat-label">xPts</div>
              <div class="cap-stat-val">{xpts:.2f}</div>
            </div>
            <div style="text-align:center;">
              <div class="cap-stat-label">Consist.</div>
              <div class="cap-stat-val">{cons_str}</div>
            </div>
            <div style="text-align:center;">
              <div class="cap-stat-label">Precio</div>
              <div class="cap-stat-val">${price:.1f}M</div>
            </div>
            <div class="fdr-chip fdr-{fdr}" style="background:{fdr_col};color:#fff;min-width:52px;text-align:center;">{opp_short} FDR{fdr}</div>
          </div>
        </div>"""

    return f"""
    <div id="captain-card">
      <div class="cap-header">
        <div class="cap-title">&#9733; Capitán Recomendado</div>
        <div class="cap-subtitle">Cap Score = xPts × consistencia × multiplicador posicional</div>
      </div>
      {rows}
    </div>"""

captain_html = build_captain_card_html(player_list)


def compute_dt_recommendations():
    """
    Poisson model to estimate P(win), P(draw), P(loss) for each team's next fixture.
    EV = P(win)*1 + P(draw)*0 + P(loss)*(-1) = P(win) - P(loss)
    λ_home_scores = blend_att(home) * (away.xgc_pg / LEAGUE_AVG) * 1.15
    λ_away_scores = blend_att(away) * (home.xgc_pg / LEAGUE_AVG) * 0.85
    """
    from math import exp, factorial

    def poisson_pmf(k, lam):
        if lam <= 0: lam = 0.01
        return exp(-lam) * (lam ** k) / factorial(k)

    def match_probs(lam_h, lam_a, max_goals=6):
        ph, pa = {}, {}
        for k in range(max_goals + 1):
            ph[k] = poisson_pmf(k, lam_h)
            pa[k] = poisson_pmf(k, lam_a)
        p_home_win = sum(ph[i]*pa[j] for i in range(max_goals+1) for j in range(max_goals+1) if i > j)
        p_draw     = sum(ph[i]*pa[i] for i in range(max_goals+1))
        p_away_win = sum(ph[i]*pa[j] for i in range(max_goals+1) for j in range(max_goals+1) if i < j)
        return p_home_win, p_draw, p_away_win

    results = []
    for fix in FIXTURES:
        home, away = fix["home"], fix["away"]
        ts_h = team_stats.get(home, {})
        ts_a = team_stats.get(away, {})

        att_h = ts_h.get("xg_pg", LEAGUE_AVG_GC_PG) * 0.65 + ts_h.get("gf_pg", LEAGUE_AVG_GC_PG) * 0.35
        att_a = ts_a.get("xg_pg", LEAGUE_AVG_GC_PG) * 0.65 + ts_a.get("gf_pg", LEAGUE_AVG_GC_PG) * 0.35
        def_h = ts_h.get("xgc_pg", LEAGUE_AVG_GC_PG)
        def_a = ts_a.get("xgc_pg", LEAGUE_AVG_GC_PG)

        lam_h = att_h * (def_a / max(LEAGUE_AVG_GC_PG, 0.01)) * 1.15
        lam_a = att_a * (def_h / max(LEAGUE_AVG_GC_PG, 0.01)) * 0.85

        p_hw, p_d, p_aw = match_probs(lam_h, lam_a)

        results.append({
            "team": home, "coach": COACHES.get(home, home),
            "opp": away,  "is_home": True,
            "p_win": p_hw, "p_draw": p_d, "p_loss": p_aw,
            "ev": round(p_hw - p_aw, 3),
            "lam_scored": round(lam_h, 2), "lam_conceded": round(lam_a, 2),
            "date": fix.get("date", ""),
        })
        results.append({
            "team": away, "coach": COACHES.get(away, away),
            "opp": home,  "is_home": False,
            "p_win": p_aw, "p_draw": p_d, "p_loss": p_hw,
            "ev": round(p_aw - p_hw, 3),
            "lam_scored": round(lam_a, 2), "lam_conceded": round(lam_h, 2),
            "date": fix.get("date", ""),
        })

    results.sort(key=lambda x: x["ev"], reverse=True)
    return results


def build_dt_card_html(n=3):
    recs = compute_dt_recommendations()[:n]
    EV_COLORS  = [(0.25, "#16a34a"), (0.10, "#65a30d"), (0.0, "#f59e0b"), (-99, "#dc2626")]

    rows = ""
    for rank, r in enumerate(recs, 1):
        ev     = r["ev"]
        coach  = r["coach"]
        team   = r["team"]
        opp    = r["opp"]
        vicon  = "🏠" if r["is_home"] else "✈️"
        date_s = r["date"]
        p_win  = r["p_win"]
        p_draw = r["p_draw"]
        p_loss = r["p_loss"]

        ev_col = next(c for thr, c in EV_COLORS if ev >= thr)
        ev_sign = f"+{ev:.3f}" if ev >= 0 else f"{ev:.3f}"
        opp_short = opp.split(" ")[0][:10]
        is_top = ' style="background:#f0fdf4;border:1.5px solid #86efac;"' if rank == 1 else ""
        medal  = ["🥇","🥈","🥉"][rank - 1]

        rows += f"""
        <div class="dt-row"{is_top}>
          <div class="dt-rank">{medal}</div>
          <div style="flex:1;min-width:0;">
            <div class="dt-coach">{coach}</div>
            <div class="dt-team">{team} {vicon} vs {opp_short} · {date_s}</div>
          </div>
          <div style="display:flex;align-items:center;gap:16px;flex-shrink:0;">
            <div style="text-align:center;">
              <div class="dt-stat-label">P(Gana)</div>
              <div class="dt-stat-val" style="color:#16a34a;">{p_win*100:.0f}%</div>
            </div>
            <div style="text-align:center;">
              <div class="dt-stat-label">P(Empate)</div>
              <div class="dt-stat-val" style="color:#f59e0b;">{p_draw*100:.0f}%</div>
            </div>
            <div style="text-align:center;">
              <div class="dt-stat-label">P(Pierde)</div>
              <div class="dt-stat-val" style="color:#dc2626;">{p_loss*100:.0f}%</div>
            </div>
            <div style="text-align:center;min-width:56px;">
              <div class="dt-stat-label">EV</div>
              <div class="dt-stat-val" style="color:{ev_col};font-size:16px;">{ev_sign}</div>
            </div>
          </div>
        </div>"""

    return f"""
    <div id="dt-card">
      <div class="dt-header">
        <div class="dt-title">&#9878; Director Técnico Recomendado</div>
        <div class="dt-subtitle">EV = P(victoria) − P(derrota) · Modelo Poisson con xG e historial</div>
      </div>
      {rows}
    </div>"""


dt_html = build_dt_card_html()




# ── STEP 6: HTML ───────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>LPF Fantasy Analytics | Apertura 2026</title>
<meta property="og:title"       content="LPF Fantasy Analytics | Apertura 2026"/>
<meta property="og:description" content="Análisis probabilístico de jugadores para Fantasy Manager Argentina — basado en metodología Opta/FPL."/>
<meta property="og:type"        content="website"/>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#f8fafc;font-family:'Segoe UI',Arial,sans-serif;color:#0f172a;min-width:320px;}

/* ── HEADER ── */
#header{background:#ffffff;border-bottom:2px solid #1a56db;padding:18px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.header-left{display:flex;align-items:center;gap:14px;}
.badge-lpf{background:#1a56db;color:#ffffff;font-weight:800;font-size:11px;padding:4px 10px;border-radius:4px;letter-spacing:.6px;}
.header-title h1{font-size:22px;font-weight:700;color:#0f172a;}
.header-title p{font-size:12px;color:#64748b;margin-top:2px;}
.header-meta{text-align:right;font-size:11px;color:#94a3b8;}
.header-meta span{color:#1a56db;font-weight:600;}

/* ── MAIN ── */
#main{max-width:1300px;margin:0 auto;padding:24px 20px 60px;}

/* ── SECTION TITLE ── */
.sec-title{font-size:13px;font-weight:700;color:#1a56db;letter-spacing:.5px;text-transform:uppercase;border-left:3px solid #1a56db;padding-left:10px;margin-bottom:16px;}

/* ── CAPTAIN CARD ── */
#captain-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.05);margin-bottom:24px;overflow:hidden;}
.cap-header{background:linear-gradient(135deg,#1a56db 0%,#1e40af 100%);padding:14px 20px;display:flex;align-items:baseline;gap:16px;}
.cap-title{font-size:15px;font-weight:700;color:#fff;letter-spacing:.3px;}
.cap-subtitle{font-size:11px;color:rgba(255,255,255,.75);}
.cap-row{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid #f1f5f9;}
.cap-row:last-child{border-bottom:none;}
.cap-rank{font-size:20px;width:28px;flex-shrink:0;}
.cap-avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0;}
.cap-name{font-size:13px;font-weight:600;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.cap-club{font-size:11px;color:#64748b;}
.cap-stat-label{font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;}
.cap-stat-val{font-size:14px;font-weight:700;color:#0f172a;}

/* ── DT CARD ── */
#dt-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.05);margin-bottom:24px;overflow:hidden;}
.dt-header{background:linear-gradient(135deg,#065f46 0%,#047857 100%);padding:14px 20px;display:flex;align-items:baseline;gap:16px;}
.dt-title{font-size:15px;font-weight:700;color:#fff;letter-spacing:.3px;}
.dt-subtitle{font-size:11px;color:rgba(255,255,255,.75);}
.dt-row{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid #f1f5f9;}
.dt-row:last-child{border-bottom:none;}
.dt-rank{font-size:20px;width:28px;flex-shrink:0;}
.dt-coach{font-size:13px;font-weight:700;color:#0f172a;}
.dt-team{font-size:11px;color:#64748b;margin-top:2px;}
.dt-stat-label{font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;}
.dt-stat-val{font-size:14px;font-weight:700;color:#0f172a;}

/* ── AVAILABILITY REVIEW ── */
#avail-review{background:#fff;border:1px solid #fcd34d;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.05);margin-bottom:28px;overflow:hidden;}
.avail-header{background:linear-gradient(135deg,#92400e 0%,#b45309 100%);padding:14px 20px;display:flex;align-items:baseline;gap:16px;}
.avail-title{font-size:15px;font-weight:700;color:#fff;letter-spacing:.3px;}
.avail-subtitle{font-size:11px;color:rgba(255,255,255,.75);}
.avail-body{padding:16px 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:16px;}
.avail-team-block{border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;}
.avail-team-header{background:#f8fafc;padding:8px 12px;font-size:12px;font-weight:700;color:#1e293b;border-bottom:1px solid #e2e8f0;}
.avail-fix-label{font-weight:400;color:#64748b;margin-left:8px;font-size:11px;}
.avail-table{width:100%;border-collapse:collapse;font-size:12px;}
.avail-table th{padding:5px 8px;background:#f1f5f9;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:.4px;text-align:left;border-bottom:1px solid #e2e8f0;}
.avail-table td{padding:5px 8px;border-bottom:1px solid #f1f5f9;color:#0f172a;}
.avail-table tr:last-child td{border-bottom:none;}
.avail-pos{background:#e2e8f0;color:#475569;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:600;}
.avail-status{border-radius:4px;padding:2px 6px;font-size:10px;font-weight:600;}

/* ── LEADERS BAR ── */
#leaders-bar{display:flex;gap:0;overflow-x:auto;margin-bottom:28px;border:1px solid #e2e8f0;border-radius:12px;background:#ffffff;box-shadow:0 1px 4px rgba(0,0,0,.05);}
.leader-card{flex:0 0 auto;min-width:200px;padding:14px 16px;border-right:1px solid #e2e8f0;position:relative;}
.leader-card:last-child{border-right:none;}
.leader-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;border-radius:12px 0 0 12px;}
.lc-xpts::before{background:#1a56db;}
.lc-xg::before{background:#10b981;}
.lc-xa::before{background:#f59e0b;}
.lc-pvi::before{background:#8b5cf6;}
.lc-val::before{background:#ef4444;}
.lc-best::before{background:#0ea5e9;}
.leader-cat{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.5px;text-transform:uppercase;margin-bottom:8px;padding-left:8px;}
.leader-row{display:flex;align-items:center;gap:6px;padding:3px 0;padding-left:8px;}
.leader-rank{font-size:10px;font-weight:700;color:#cbd5e1;min-width:14px;}
.leader-info{flex:1;min-width:0;}
.leader-name{font-size:11px;font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.leader-club-tag{font-size:9px;color:#94a3b8;font-weight:500;}
.leader-val{font-size:12px;font-weight:800;color:#1a56db;min-width:38px;text-align:right;}

/* ── TOP PICKS ── */
#top-picks-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-bottom:32px;}
.pick-card{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;border-top:3px solid #1a56db;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.pick-card.pick-G{border-top-color:#8b5cf6;}
.pick-card.pick-D{border-top-color:#10b981;}
.pick-card.pick-M{border-top-color:#1a56db;}
.pick-card.pick-F{border-top-color:#f97316;}
.pick-pos-label{font-size:10px;font-weight:700;color:#64748b;letter-spacing:.5px;text-transform:uppercase;margin-bottom:8px;}
.pick-name{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:2px;line-height:1.2;}
.pick-club{font-size:11px;color:#64748b;margin-bottom:10px;}
.pick-xpts{font-size:26px;font-weight:800;color:#1a56db;line-height:1;}
.pick-xpts-label{font-size:10px;color:#94a3b8;margin-bottom:8px;}
.pick-stats{display:flex;gap:12px;font-size:11px;}
.pick-stat{color:#64748b;}.pick-stat span{color:#0f172a;font-weight:600;}
.pick-fixture{font-size:10px;margin-top:8px;color:#94a3b8;}

/* ── FIXTURE CARDS ── */
#fixtures-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:32px;}
.fx-card{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.04);}

/* ── TOOLTIPS ── */
[data-tip]{position:relative;cursor:help;}
[data-tip]::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);
  background:#1e293b;color:#f1f5f9;font-size:11px;font-weight:400;padding:7px 11px;border-radius:7px;
  white-space:normal;width:260px;text-align:left;pointer-events:none;opacity:0;transition:opacity .15s;
  z-index:200;letter-spacing:normal;text-transform:none;line-height:1.45;border:1px solid #334155;}
[data-tip]:hover::after{opacity:1;}
/* Table headers: tooltip below (headers are at top of viewport) */
th[data-tip]::after{bottom:auto;top:calc(100% + 6px);}

.fx-round{font-size:10px;font-weight:700;color:#64748b;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px;}
.fx-matchup{display:flex;align-items:center;justify-content:space-between;gap:8px;}
.fx-team{flex:1;}
.fx-team-name{font-size:13px;font-weight:700;color:#0f172a;line-height:1.2;}
.fx-team-tag{font-size:10px;color:#64748b;margin-top:2px;}
.fx-vs{font-size:11px;font-weight:700;color:#94a3b8;padding:0 4px;}
.fx-fdr-row{display:flex;gap:8px;margin-top:12px;}
.fdr-chip{flex:1;text-align:center;padding:5px 4px;border-radius:6px;font-size:11px;font-weight:700;}
.fdr-1{background:#00c853;color:#fff;}
.fdr-2{background:#69f0ae;color:#064e3b;}
.fdr-3{background:#fff9c4;color:#78350f;border:1px solid #fde047;}
.fdr-4{background:#ff9800;color:#fff;}
.fdr-5{background:#f44336;color:#fff;}

/* ── TABS / POSITION FILTER PILLS ── */
.tabs{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap;}
.tab{background:#f1f5f9;border:1.5px solid #e2e8f0;color:#64748b;font-size:12px;font-weight:600;padding:6px 16px;border-radius:20px;cursor:pointer;transition:all .15s;}
.tab:hover{border-color:#1a56db;color:#1a56db;background:#eff6ff;}
.tab.active{background:#1a56db;color:#ffffff;border-color:#1a56db;}

/* ── PLAYER TABLE ── */
.search-row{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;align-items:center;}
#search-input{flex:1;min-width:180px;background:#ffffff;border:1.5px solid #e2e8f0;color:#0f172a;padding:8px 12px;border-radius:20px;font-size:13px;outline:none;box-shadow:0 1px 2px rgba(0,0,0,.04);}
#search-input:focus{border-color:#1a56db;box-shadow:0 0 0 3px rgba(26,86,219,.1);}
#search-input::placeholder{color:#94a3b8;}
.sort-select{background:#ffffff;border:1.5px solid #e2e8f0;color:#64748b;padding:7px 10px;border-radius:8px;font-size:12px;cursor:pointer;outline:none;}
.sort-select:focus{border-color:#1a56db;}

.tbl-wrap{overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.05);}
table{width:100%;border-collapse:collapse;font-size:12.5px;min-width:700px;}
thead th{background:#f8fafc;color:#64748b;padding:10px 10px;text-align:left;font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;white-space:nowrap;cursor:pointer;user-select:none;border-bottom:2px solid #e2e8f0;position:sticky;top:0;z-index:2;}
thead th:first-child{position:sticky;left:0;z-index:3;background:#f8fafc;}
thead th:hover{color:#1a56db;}
thead th.sort-asc::after{content:" ▲";font-size:8px;color:#1a56db;}
thead th.sort-desc::after{content:" ▼";font-size:8px;color:#1a56db;}
tbody tr:nth-child(even){background:#f8fafc;}
tbody tr:nth-child(odd){background:#ffffff;}
tbody tr:hover{background:#e8f4fd !important;}
tbody tr{border-bottom:1px solid #f1f5f9;}
td{padding:8px 10px;white-space:nowrap;vertical-align:middle;}
td:first-child{position:sticky;left:0;z-index:1;background:inherit;}

/* ── PLAYER AVATAR ── */
.player-cell{display:flex;align-items:center;gap:9px;}
.player-avatar{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0;color:#fff;}
.av-G{background:#8b5cf6;}
.av-D{background:#10b981;}
.av-M{background:#1a56db;}
.av-F{background:#f97316;}
.player-name{font-weight:700;color:#0f172a;}
.club-tag{font-size:11px;color:#64748b;}

/* ── BADGES ── */
.pos-badge{display:inline-block;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700;}
.pos-G{background:#ede9fe;color:#6d28d9;}
.pos-D{background:#d1fae5;color:#065f46;}
.pos-M{background:#dbeafe;color:#1e40af;}
.pos-F{background:#ffedd5;color:#c2410c;}
.home-tag{background:#dbeafe;color:#1e40af;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;}
.away-tag{background:#f1f5f9;color:#64748b;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;}
.pen-badge{display:inline-block;font-size:9px;font-weight:800;padding:1px 4px;border-radius:3px;margin-left:5px;background:#dbeafe;color:#1e40af;vertical-align:middle;letter-spacing:.2px;}
.sp-badge{display:inline-block;font-size:9px;font-weight:800;padding:1px 4px;border-radius:3px;margin-left:4px;background:#d1fae5;color:#065f46;vertical-align:middle;letter-spacing:.2px;}
.form-badge{display:inline-block;font-size:9px;font-weight:800;padding:1px 4px;border-radius:3px;margin-left:4px;background:#ede9fe;color:#6d28d9;vertical-align:middle;letter-spacing:.2px;}
.doubt-badge{display:inline-block;font-size:9px;font-weight:800;padding:1px 5px;border-radius:3px;margin-left:4px;background:#fef3c7;color:#92400e;border:1px solid #fcd34d;vertical-align:middle;letter-spacing:.2px;}
.role-Duda{background:#fef3c7;color:#92400e;border:1px dashed #fcd34d;}
.cons-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:5px;vertical-align:middle;flex-shrink:0;}
.cons-high{background:#10b981;}
.cons-mid{background:#f59e0b;}
.cons-low{background:#ef4444;}
.xsv-tag{font-size:10px;color:#94a3b8;margin-top:2px;}
.role-badge{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-top:3px;letter-spacing:.2px;}
.role-Titular{background:#d1fae5;color:#065f46;}
.role-Rotacional{background:#fef9c3;color:#854d0e;}
.role-Suplente{background:#fee2e2;color:#991b1b;}
.fdr-vuln{font-size:10px;color:#f59e0b;margin-top:3px;letter-spacing:.2px;}

/* ── PROB BARS ── */
.prob-cell{min-width:90px;}
.prob-bar-wrap{display:flex;align-items:center;gap:6px;}
.prob-val{font-size:11px;font-weight:700;min-width:34px;text-align:right;color:#0f172a;}
.prob-bar{flex:1;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;}
.prob-fill{height:100%;border-radius:3px;}
.fill-goal{background:#ef4444;}
.fill-assist{background:#1a56db;}
.fill-cs{background:#10b981;}
.xpts-val{font-size:14px;font-weight:800;color:#1a56db;}

/* ── FDR TABLE ── */
#fdr-section{margin-top:36px;}
.fdr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;}
.fdr-row-card{background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;display:flex;align-items:center;gap:12px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
.fdr-badge-big{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:900;flex-shrink:0;}
.fdr-info{flex:1;min-width:0;}
.fdr-club{font-size:12px;font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fdr-stats{font-size:10.5px;color:#64748b;margin-top:2px;}
.fdr-score-bar{height:3px;border-radius:2px;margin-top:5px;background:#e2e8f0;overflow:hidden;}
.fdr-score-fill{height:100%;border-radius:2px;}

/* ── SIMULATOR ── */
#sim-section{margin-top:36px;}
.sim-controls{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.sim-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.sim-label{font-size:12px;font-weight:600;color:#64748b;min-width:70px;}
.sim-select{background:#f8fafc;border:1.5px solid #e2e8f0;color:#0f172a;padding:8px 12px;border-radius:7px;font-size:13px;cursor:pointer;outline:none;min-width:200px;}
.sim-select:focus{border-color:#1a56db;}
.sim-toggle{display:flex;gap:6px;}
.sim-toggle button{background:#f1f5f9;border:1.5px solid #e2e8f0;color:#64748b;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;}
.sim-toggle button.active{background:#1a56db;color:#ffffff;border-color:#1a56db;}
#sim-run-btn{background:#1a56db;color:#ffffff;border:none;padding:9px 20px;border-radius:7px;font-size:13px;font-weight:700;cursor:pointer;}
#sim-run-btn:hover{background:#1648c0;}
#sim-results{display:none;}
.sim-top-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:16px;}
.sim-player-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;}
.sim-player-name{font-size:13px;font-weight:700;color:#0f172a;margin-bottom:2px;}
.sim-player-sub{font-size:11px;color:#64748b;margin-bottom:8px;}
.sim-probs{display:flex;flex-direction:column;gap:4px;}
.sim-prob-row{display:flex;justify-content:space-between;font-size:11px;}
.sim-prob-label{color:#64748b;}
.sim-prob-val{font-weight:700;color:#0f172a;}

/* ── METHODOLOGY ── */
#method-section{margin-top:40px;background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:22px 24px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
#method-section h3{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:14px;}
.method-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;}
.method-card{background:#f8fafc;border-radius:8px;padding:14px 16px;border:1px solid #e2e8f0;}
.method-card h4{font-size:12px;font-weight:700;color:#1a56db;margin-bottom:6px;}
.method-card p{font-size:11.5px;color:#64748b;line-height:1.5;}
.method-formula{background:#f1f5f9;border-left:3px solid #1a56db;padding:8px 12px;border-radius:0 6px 6px 0;margin-top:8px;font-family:monospace;font-size:11px;color:#64748b;}

/* ── FOOTER ── */
#footer{background:#f1f5f9;border-top:1px solid #e2e8f0;padding:16px 28px;text-align:center;font-size:11px;color:#94a3b8;margin-top:10px;}
#footer a{color:#1a56db;text-decoration:none;}

/* ── RESPONSIVE ── */
@media(max-width:640px){
  #header{flex-direction:column;align-items:flex-start;}
  .header-meta{text-align:left;}
  .sim-row{flex-direction:column;align-items:flex-start;}
}
</style>
</head>
<body>

<div id="header">
  <div class="header-left">
    <div>
      <span class="badge-lpf">LPF</span>
    </div>
    <div class="header-title">
      <h1>Fantasy Analytics</h1>
      <p>Liga Profesional Argentina · Apertura 2026</p>
    </div>
  </div>
  <div class="header-meta">
    Metodología: <span>Opta · FPL Review</span><br>
    Actualizado: <span>Mayo 2026</span><br>
    <a href="https://github.com" style="color:#1a56db;font-size:11px;">Ver en GitHub</a>
  </div>
</div>

<div id="main">

  <!-- CAPTAIN CARD -->
  /*__CAPTAIN__*/

  <!-- DT CARD -->
  /*__DT__*/

  <!-- LEADERS BAR -->
  <div style="margin-bottom:28px;">
    <div class="sec-title">Top 3 por categoría</div>
    <div id="leaders-bar">/*__LEADERS__*/</div>
  </div>

  <!-- TOP PICKS -->
  <div style="margin-bottom:8px;">
    <div class="sec-title">Mejor jugador por posición — fixtures actuales</div>
    <p style="font-size:11.5px;color:#64748b;margin-bottom:14px;">El jugador con mayor xPts proyectado en cada posición, considerando rendimiento histórico y dificultad del rival.</p>
    <div id="top-picks-grid"></div>
  </div>

  <!-- FIXTURE FDR CONTEXT -->
  <div style="margin-bottom:28px;">
    <div class="sec-title" style="margin-bottom:10px;color:#64748b;border-left-color:#64748b;">Contexto de fixture — dificultad defensiva del rival</div>
    <div id="fixtures-grid"></div>
  </div>

  <!-- PLAYER PROJECTIONS -->
  <div style="margin-top:28px;">
    <div class="sec-title">Proyecciones por jugador</div>
    <p style="font-size:11.5px;color:#64748b;margin-bottom:14px;">
      xPts calculado con metodología Opta: xG/90 × debilidad defensiva del rival × ventaja de local/visitante × multiplicador de posición.
      Puntuación: gol ARQ 8pts / DEF 8pts / MED 5pts / DEL 4pts · asistencia 3pts · valla invicta ARQ 5pts / DEF 4pts / MED 1pt.
    </p>

    <div class="tabs" id="pos-tabs">
      <button class="tab active" data-pos="ALL">Todos</button>
      <button class="tab" data-pos="G">Arqueros</button>
      <button class="tab" data-pos="D">Defensores</button>
      <button class="tab" data-pos="M">Mediocampistas</button>
      <button class="tab" data-pos="F">Delanteros</button>
    </div>

    <div class="search-row">
      <input id="search-input" type="text" placeholder="Buscar jugador..."/>
      <select id="club-filter" class="sort-select">
        <option value="ALL">Todos los equipos</option>
      </select>
      <select class="sort-select" id="sort-select">
        <option value="xpts">Ordenar: xPts</option>
        <option value="p_goal">Ordenar: P(Gol)</option>
        <option value="p_assist">Ordenar: P(Asistencia)</option>
        <option value="p_cs">Ordenar: P(Valla Invicta)</option>
        <option value="cap_score">Ordenar: Captaincy Score</option>
        <option value="p_play">Ordenar: P(Titular &gt;60min)</option>
        <option value="xg_90">Ordenar: xG/90</option>
        <option value="xgi_90">Ordenar: xGI/90</option>
        <option value="npxg_90">Ordenar: npxG/90</option>
        <option value="sca_90">Ordenar: SCA/90</option>
        <option value="gca_90">Ordenar: GCA/90</option>
        <option value="prog_carries_90">Ordenar: Prog. Carries/90</option>
        <option value="xg_over">Ordenar: xG± (Overperformance)</option>
        <option value="rating">Ordenar: Rating temporada</option>
        <option value="form_rating">Ordenar: Rating últimos 5P</option>
        <option value="fm_mean_pts">Ordenar: FM Pts/PJ (real)</option>
        <option value="bpr_rate">Ordenar: BPR % (Figura)</option>
        <option value="xpts_per_m">Ordenar: xPts/M$ (valor)</option>
      </select>
    </div>

    <div class="tbl-wrap">
      <table id="player-table">
        <thead>
          <tr>
            <th data-col="name">Jugador</th>
            <th data-col="pos">Pos</th>
            <th data-col="opp" data-tip="Rival en el fixture y su FDR (Fixture Difficulty Rating). FDR 1: defensa muy débil (+30–50% en P(Gol)). FDR 2: defensa floja (+12–30%). FDR 3: fixture neutro (±12%). FDR 4: defensa sólida (−6–22%). FDR 5: defensa élite (−22–50%). Pasá el mouse sobre el chip del rival para ver sus stats defensivos exactos.">Rival (?)</th>
            <th data-col="xpts" class="sort-desc" data-tip="Puntos esperados (Expected Points). Es el promedio ponderado de todos los eventos posibles: xPts = P(Gol)×pts + P(Asistencia)×3 + P(VI)×pts + Minutos − Tarjetas + E[BPR]. Pasá el mouse sobre el número para ver el desglose.">xPts ↓ (?)</th>
            <th data-col="xpts_per_m" data-tip="xPts por millón invertido (valor). Métrica Opta de eficiencia presupuestaria: cuántos puntos esperados generás por cada millón que cuesta el jugador. Útil para encontrar los mejores picks dentro de las restricciones de presupuesto.">xPts/M$ (?)</th>
            <th data-col="cap_score" data-tip="Captaincy Score: xPts ponderado por consistencia. Dos jugadores con igual xPts pero distinta consistencia tendrán diferente Cap Score — el más consistente es mejor capitán porque tiene menor riesgo de output bajo.">Cap (?)</th>
            <th data-col="p_play" data-tip="Probabilidad de jugar más de 60 minutos. Fórmula Opta: disponibilidad histórica (partidos jugados / total del equipo) × P(&gt;60 | juega). P(&gt;60|juega) varía por posición: ARQ=0.96 fijo (los arqueros no se cambian), DEF umbral bajo (raramente salen antes del 60'), MED y DEL escala por minutos promedio. Si un jugador perdió partidos por lesión, su disponibilidad baja — el modelo no distingue el motivo.">P(+60') (?)</th>
            <th data-col="p_goal" data-tip="Probabilidad de marcar un gol en este partido. Calculada con xG/90 del jugador ajustado por la debilidad defensiva del rival, ventaja de local/visitante y rol posicional. No es garantía — es el valor esperado por partido.">P(Gol) (?)</th>
            <th data-col="p_assist" data-tip="Probabilidad de dar una asistencia. Basada en xA/90 del jugador con los mismos ajustes que P(Gol). Los mediocampistas y extremos tienen el mayor coeficiente por posición.">P(Asist) (?)</th>
            <th data-col="p_cs" data-tip="Probabilidad de Valla Invicta (clean sheet). Calculada combinando el % histórico de VI del propio equipo (65%) con el balance entre defensa propia y ataque rival del fixture (35%). Solo aplica a ARQ, DEF y MED.">P(VI) (?)</th>
            <th data-col="xg_90" data-tip="Expected Goals por 90 minutos (incluye penales). Blended: 60% temporada + 40% últimos 5 partidos cuando hay datos de forma.">xG/90 (?)</th>
            <th data-col="npxg_90" data-tip="Non-Penalty xG por 90 minutos. Igual que xG/90 pero sin contar el xG de los penales. Mejor indicador de la calidad finalizadora real del jugador, sin ruido del rol de ejecutante.">npxG/90 (?)</th>
            <th data-col="xa_90" data-tip="Expected Assists por 90 minutos. Mide la calidad de los pases que generaron ocasiones de gol, normalizada a 90 minutos. Combina ubicación del pase, tipo y posición del receptor.">xA/90 (?)</th>
            <th data-col="xgi_90" data-tip="xG Involvement por 90 minutos: xG/90 + xA/90 combinados (post-blend). Mide el involucramiento total en la generación de gol. Útil para identificar jugadores de alto output que balancean goles y asistencias.">xGI/90 (?)</th>
            <th data-col="sca_90" data-tip="Shot Creating Actions por 90 minutos: acciones que generaron un remate (pases clave + goles + asistencias). Mide cuántas veces por partido crea situaciones de disparo. Proxy con datos SofaScore.">SCA/90 (?)</th>
            <th data-col="gca_90" data-tip="Goal Creating Actions por 90 minutos: acciones que generaron una gran chance de gol (grandes chances creadas + goles + asistencias). Versión más exigente que SCA — solo cuenta las ocasiones claras.">GCA/90 (?)</th>
            <th data-col="prog_carries_90" data-tip="Regates exitosos por 90 minutos. Proxy de progressive carries — carreras con el balón que superan a un rival y avanzan el juego. Alta correlación con creación de peligro en ataque posicional.">Prog.C/90 (?)</th>
            <th data-col="style_match" data-tip="Match de estilo vs. defensa rival. Mide cuánto el perfil ofensivo del jugador (box runner, playmaker, etc.) explota la vulnerabilidad específica del rival. Verde = el rival es débil frente al estilo de este jugador. Rojo = el rival es fuerte ante ese perfil.">Match (?)</th>
            <th data-col="bpr_rate" data-tip="Porcentaje de fechas en que el jugador ganó el BPR (Bonus por Rendimiento / Figura). Incorporado al xPts como E[BPR pts] = tasa × avg_pts × disponibilidad. Jugadores con alta tasa de BPR tienen un boost real en sus puntos esperados.">BPR % (?)</th>
            <th data-col="goals" data-tip="Goles marcados en la temporada actual (Primera LPF 2026).">G</th>
            <th data-col="assists" data-tip="Asistencias en la temporada actual (Primera LPF 2026).">A</th>
            <th data-col="xg_over" data-tip="xG Overperformance: Goles reales menos xG acumulado. Positivo (+) = el jugador marcó más de lo esperado (puede ser suerte o habilidad finalizadora excepcional). Negativo (−) = marcó menos de lo esperado, está en deuda con el xG — candidato a entrar en racha. Solo visible cuando SofaScore provee xG real.">xG± (?)</th>
            <th data-col="rating" data-tip="Rating promedio de temporada según SofaScore (escala 1–10). Rating acumulado de todos los partidos jugados en el Apertura 2026.">Rating (temp.) (?)</th>
            <th data-col="form_rating" data-tip="Rating promedio en los últimos 5 partidos del Apertura 2026 (SofaScore). Más representativo del momento actual del jugador que el rating de temporada. Solo cuenta partidos con más de 20 minutos jugados.">Rating (5P) (?)</th>
            <th data-col="fm_mean_pts" data-tip="Promedio real de puntos en Fantasy Manager AR durante el Apertura 2026. Incluye todos los eventos: goles, asistencias, valla invicta, minutos y BPR (Bonus por Rendimiento). Es el benchmark empírico contra el que comparamos nuestro xPts.">FM Pts/PJ (?)</th>
          </tr>
        </thead>
        <tbody id="player-tbody"></tbody>
      </table>
    </div>
    <p id="row-count" style="font-size:11px;color:#94a3b8;margin-top:8px;"></p>
  </div>

  <!-- FDR TABLE -->
  <div id="fdr-section">
    <div class="sec-title">Índice de dificultad de fixture (FDR) — todos los equipos</div>
    <p style="font-size:11.5px;color:#64748b;margin-bottom:14px;">
      FDR mide la dificultad de atacar a ese equipo. <b style="color:#10b981">FDR 1–2</b>: defensa débil, P(Gol) sube hasta +50%.
      <b style="color:#f59e0b">FDR 3</b>: fixture neutro. <b style="color:#f97316">FDR 4</b>: defensa sólida, P(Gol) baja entre −6% y −22%.
      <b style="color:#ef4444">FDR 5</b>: defensa élite, P(Gol) baja hasta −50%. Calculado con xGC/partido (65%) + tasa de vallas invictas (35%).
      Pasá el mouse sobre el chip del rival en la tabla para ver el score defensivo exacto y el impacto en las proyecciones.
    </p>
    <div class="fdr-grid" id="fdr-grid"></div>
  </div>

  <!-- SIMULATOR -->
  <div id="sim-section">
    <div class="sec-title">Simulador de fixture</div>
    <p style="font-size:11.5px;color:#64748b;margin-bottom:14px;">
      Seleccioná cualquier enfrentamiento para ver las proyecciones de ambos equipos.
      Útil para fechas futuras o torneos que aún no tienen fixtures definidos.
    </p>
    <div class="sim-controls">
      <div class="sim-row" style="margin-bottom:12px;">
        <span class="sim-label">Local</span>
        <select class="sim-select" id="sim-home"></select>
        <div class="sim-toggle" id="home-toggle">
          <button class="active" data-val="true">Local</button>
          <button data-val="false">Visitante</button>
        </div>
      </div>
      <div class="sim-row" style="margin-bottom:12px;">
        <span class="sim-label">Visitante</span>
        <select class="sim-select" id="sim-away"></select>
      </div>
      <div class="sim-row">
        <button id="sim-run-btn">Ver proyección →</button>
        <span id="sim-fdr-preview" style="font-size:12px;color:#7891b5;margin-left:8px;"></span>
      </div>
    </div>
    <div id="sim-results">
      <div class="tabs" id="sim-pos-tabs">
        <button class="tab active" data-pos="ALL">Todos</button>
        <button class="tab" data-pos="G">Arqueros</button>
        <button class="tab" data-pos="D">Defensores</button>
        <button class="tab" data-pos="M">Mediocampistas</button>
        <button class="tab" data-pos="F">Delanteros</button>
      </div>
      <div class="tbl-wrap">
        <table id="sim-table">
          <thead>
            <tr>
              <th>Jugador</th>
              <th>Club</th>
              <th>Pos</th>
              <th>L/V</th>
              <th>xPts</th>
              <th>P(Gol)</th>
              <th>P(Asist)</th>
              <th>P(VI)</th>
              <th>xG/90</th>
            </tr>
          </thead>
          <tbody id="sim-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- METHODOLOGY -->
  <div id="method-section">
    <h3>Metodología</h3>
    <div class="method-grid">
      <div class="method-card">
        <h4>P(Gol) — Probabilidad de gol</h4>
        <p>Inspirada en el modelo xG de Opta. Usa el xG acumulado del jugador normalizado a 90 minutos, ajustado por tres factores:</p>
        <div class="method-formula">xG/90 × def_rival × local/visit × pos_mult</div>
      </div>
      <div class="method-card">
        <h4>P(Asistencia)</h4>
        <p>Basada en xA/90 del jugador. Con fallback a pases clave × 0.08 cuando no hay xA disponible. Mismo ajuste por rival y posición.</p>
        <div class="method-formula">xA/90 × def_rival × local/visit × pos_mult</div>
      </div>
      <div class="method-card">
        <h4>P(Valla Invicta)</h4>
        <p>Depende del balance entre la defensa del propio equipo y el poder ofensivo del rival. Aplica solo a ARQ, DEF y MED.</p>
        <div class="method-formula">(def_propio − ataque_rival + 100) / 200 × factor_local</div>
      </div>
      <div class="method-card">
        <h4>FDR — Dificultad de fixture</h4>
        <p>Defense Score calculado con goles concedidos/partido (65%) y tasa de vallas invictas (35%). Convertido a escala 1–5.</p>
        <div class="method-formula">gc_pg × −52 + vi_rate × 1.3 → normalizado 0–100 → FDR 1–5</div>
      </div>
      <div class="method-card">
        <h4>xPts — Puntos esperados</h4>
        <p>Combina todas las probabilidades con la puntuación de Fantasy Manager Argentina. Incluye penalización por promedio de tarjetas.</p>
        <div class="method-formula">P(G)×pts_gol + P(A)×3 + P(VI)×pts_vi + mins_pts + card_pen</div>
      </div>
      <div class="method-card">
        <h4>Fuentes de datos</h4>
        <p>Stats de jugadores: SofaScore + FotMob (Opta). Cobertura: Primera LPF 2026, 30 equipos, ~580 jugadores con minutos.</p>
        <div class="method-formula">Datos al 05/05/2026 · No garantiza resultados</div>
      </div>
    </div>
  </div>

</div><!-- /main -->

<div id="footer">
  Fuentes: <a href="https://www.sofascore.com" target="_blank">SofaScore</a> · <a href="https://www.fotmob.com" target="_blank">FotMob (Opta)</a> · <a href="https://www.ligaprofesional.ar" target="_blank">Liga Profesional</a>
  &nbsp;·&nbsp; Metodología inspirada en Opta / FPL Review
  &nbsp;·&nbsp; <strong style="color:#0f172a;">No reemplaza análisis profesional · Uso informativo</strong>
</div>

<script>
const D = /*__DATA__*/;

const FDR_COLORS = {1:"fdr-1",2:"fdr-2",3:"fdr-3",4:"fdr-4",5:"fdr-5"};
const FDR_LABELS = {1:"FDR 1 · Fácil",2:"FDR 2 · Accesible",3:"FDR 3 · Medio",4:"FDR 4 · Difícil",5:"FDR 5 · Muy difícil"};
const POS_LABELS = {G:"Arquero",D:"Defensor",M:"Mediocampista",F:"Delantero"};

// ── Render Top Picks ──────────────────────────────────────────────────────
function renderTopPicks(){
  const grid = document.getElementById("top-picks-grid");
  grid.innerHTML = "";
  const positions = ["G","D","M","F"];
  const posColors = {G:"#8b5cf6",D:"#10b981",M:"#1a56db",F:"#f97316"};
  positions.forEach(pos=>{
    const best = D.players.filter(p=>p.pos===pos).sort((a,b)=>b.xpts-a.xpts)[0];
    if(!best) return;
    const fdrCls = FDR_COLORS[best.fdr_opp]||"fdr-3";
    const lv = best.is_home?"🏠 Local":"✈ Visit.";
    const card = document.createElement("div");
    card.className = `pick-card pick-${pos}`;
    card.innerHTML = `
      <div class="pick-pos-label">${POS_LABELS[pos]}</div>
      <div class="pick-name">${best.name}</div>
      <div class="pick-club">${best.club}</div>
      <div class="pick-xpts">${best.xpts}</div>
      <div class="pick-xpts-label">xPts esperados</div>
      <div class="pick-stats">
        <span class="pick-stat">P(G) <span>${best.p_goal}%</span></span>
        <span class="pick-stat">P(A) <span>${best.p_assist}%</span></span>
        <span class="pick-stat">P(VI) <span>${best.p_cs}%</span></span>
      </div>
      <div class="pick-fixture"><span class="fdr-chip ${fdrCls}" style="font-size:10px;padding:2px 6px;">vs ${best.opp.split(" ")[0]} · FDR${best.fdr_opp}</span> ${lv}</div>`;
    grid.appendChild(card);
  });
}

// ── Render Fixtures ────────────────────────────────────────────────────────
function renderFixtures(){
  const grid = document.getElementById("fixtures-grid");
  grid.innerHTML = "";
  D.fixtures.forEach(fx=>{
    const hd = D.team_stats[fx.home]||{};
    const ad = D.team_stats[fx.away]||{};
    const hFdr = hd.fdr||3, aFdr = ad.fdr||3;
    const card = document.createElement("div");
    card.className = "fx-card";
    card.innerHTML = `
      <div class="fx-round">${fx.date||fx.round}</div>
      <div class="fx-matchup">
        <div class="fx-team">
          <div class="fx-team-name">${fx.home}</div>
          <div class="fx-team-tag">🏠 Local</div>
        </div>
        <div class="fx-vs">vs</div>
        <div class="fx-team" style="text-align:right">
          <div class="fx-team-name">${fx.away}</div>
          <div class="fx-team-tag">✈ Visitante</div>
        </div>
      </div>
      <div class="fx-fdr-row">
        <div class="fdr-chip ${FDR_COLORS[aFdr]}">${fx.home.split(" ")[0]} ataca · FDR ${aFdr}</div>
        <div class="fdr-chip ${FDR_COLORS[hFdr]}">${fx.away.split(" ")[0]} ataca · FDR ${hFdr}</div>
      </div>`;
    grid.appendChild(card);
  });
}

// ── Prob bar helper ────────────────────────────────────────────────────────
function probBar(val, cls){
  const pct = Math.min(100,val);
  return `<div class="prob-cell"><div class="prob-bar-wrap">
    <span class="prob-val">${val}%</span>
    <div class="prob-bar"><div class="prob-fill ${cls}" style="width:${pct}%"></div></div>
  </div></div>`;
}

// ── Player Table ───────────────────────────────────────────────────────────
let currentPos  = "ALL";
let currentClub = "ALL";
let currentSort = "xpts";
let sortDir     = "desc";
let searchQ     = "";

// Poblar dropdown de equipos
(()=>{
  const sel = document.getElementById("club-filter");
  const clubs = [...new Set(D.players.map(p=>p.club))].sort();
  clubs.forEach(c=>{
    const opt = document.createElement("option");
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", ()=>{ currentClub = sel.value; renderPlayerTable(); });
})();

function filteredPlayers(){
  return D.players.filter(p=>{
    if(currentPos  !== "ALL" && p.pos  !== currentPos)  return false;
    if(currentClub !== "ALL" && p.club !== currentClub) return false;
    const q = searchQ.toLowerCase();
    if(q && !p.name.toLowerCase().includes(q)) return false;
    return true;
  });
}

function sortedPlayers(){
  const fp = filteredPlayers();
  return fp.sort((a,b)=>{
    let av = a[currentSort], bv = b[currentSort];
    if(av==null) av = -Infinity;
    if(bv==null) bv = -Infinity;
    if(typeof av==="string") return sortDir==="asc"?av.localeCompare(bv):bv.localeCompare(av);
    return sortDir==="asc"?av-bv:bv-av;
  });
}

function renderPlayerTable(){
  const rows = sortedPlayers();
  const tbody = document.getElementById("player-tbody");
  tbody.innerHTML = "";
  rows.forEach(p=>{
    const tr = document.createElement("tr");
    const ratingStr = p.rating!=null?p.rating.toFixed(1):"—";
    const ratingColor = p.rating>=7.5?"#10b981":p.rating>=6.5?"#f59e0b":"#ef4444";
    const fdrCls = FDR_COLORS[p.fdr_opp]||"fdr-3";
    const oppSt  = D.team_stats[p.opp]||{};
    const defScore = oppSt.def_score||50;
    const defMult  = Math.round((1.0+(50-defScore)/100)*100-100);
    const multSign = defMult>=0?"+":"";
    const fdrDescs = {1:"Defensa muy débil — fácil de atacar",2:"Defensa floja — buen fixture ofensivo",3:"Defensa media — fixture neutral",4:"Defensa sólida — difícil generar ocasiones",5:"Defensa muy sólida — el fixture más difícil del torneo"};
    const fdrTip   = `FDR ${p.fdr_opp} — ${fdrDescs[p.fdr_opp]||""}\nxGC/pj: ${oppSt.xgc_pg||oppSt.gc_pg||"?"} · VI: ${oppSt.vi_pct||"?"}% · score defensivo: ${defScore}/100\nImpacto estimado en P(Gol) y P(Asistencia): ${multSign}${defMult}% vs fixture neutro (FDR3)`;
    const lvTag = p.is_home
      ?`<span class="home-tag">🏠 Local</span>`
      :`<span class="away-tag">✈ Visit.</span>`;
    const bk = p.breakdown||{};
    const regPct = p.reg_w != null ? Math.round(p.reg_w*100) : 100;
    const penNote = p.is_pen_taker ? " | Penal: xG preservado" : "";
    const spNote  = p.is_sp_taker  ? ` | PP: ${(p.sp_role||[]).map(r=>r==="corners"?"CK":"FK").join("+")} (k=4)` : "";
    const regNote = regPct < 100   ? ` | ${p.games}pj: ${regPct}% propio / ${100-regPct}% liga` : "";
    const bkTitle = `Gol: ${bk.gol||0} | Asistencia: ${bk.asist||0} | VI: ${bk.vi||0} | Mins: ${bk.mins||0} | Tarjetas: ${bk.cards||0}${penNote}${spNote}${regNote}`;
    const roleLabel = p.role||"Titular";
    const penBadge  = p.is_pen_taker ? `<span class="pen-badge" title="Ejecutante de penales: el xG de penal se protege de la regresión a la media porque es un rol fijo, no ruido estadístico.">P</span>` : "";
    const spLabel   = p.sp_role && p.sp_role.length ? p.sp_role.map(r=>r==="corners"?"CK":"FK").join("+") : "";
    const spBadge   = p.is_sp_taker ? `<span class="sp-badge" title="Ejecutante de pelota parada (${spLabel}). Su xA elevado viene de un rol sistemático, no de suerte. Se usa k=4 en la regresión bayesiana (vs k=8 para el resto) — se confía más en su xA observado.">${spLabel}</span>` : "";
    const formBadge = p.has_form ? `<span class="form-badge" title="Forma reciente ponderada: últimos 5 partidos del Apertura 2026 con decay exponencial (0.75^i). Blend: 40% forma reciente + 60% temporada completa. Mejora la proyección para jugadores en racha o en baja forma.">FORM</span>` : "";
    const doubtLabel = p.doubt_status === "suspended" ? "SUSP" : "DUDA";
    const doubtBadge = p.doubt ? `<span class="doubt-badge" title="${p.doubt_status === 'suspended' ? 'Suspendido — no juega' : 'Lesionado — confirmar disponibilidad antes de poner'}">&#9888; ${doubtLabel}</span>` : "";
    const consCls   = p.consistency == null ? "" : p.consistency >= 70 ? "cons-high" : p.consistency >= 40 ? "cons-mid" : "cons-low";
    const consDesc  = p.consistency == null ? "Sin datos de forma suficientes" : p.consistency >= 70 ? "Consistente — output estable partido a partido" : p.consistency >= 40 ? "Variable — rinde bien a veces, flojea otras" : "Boom-or-bust — oscila mucho entre partidos";
    const consTitle = p.consistency == null ? "" : `Consistencia: ${p.consistency}/100 | ${consDesc}. Reduce xPts hasta 8% para jugadores muy irregulares. Basado en el coeficiente de variación del (xG+xA)/90 en los últimos 5 partidos.`;
    const consDot   = consCls ? `<span class="cons-dot ${consCls}" title="${consTitle}"></span>` : "";
    const xsvLine   = (p.pos === "G" && p.xSv_pg > 0) ? `<div class="xsv-tag" title="xSv ${p.xSv_pg}: atajadas esperadas por partido (tiros al arco rivales × 70% save rate media). Equipos que conceden pocos SOT/pg tienen arqueros con P(VI) más alta; muchos SOT = VI más difícil. Ajusta P(VI) ±25% vs. media de liga (3.54 SOT/pg).">xSv ${p.xSv_pg}</div>` : "";
    tr.innerHTML = `
      <td><div class="player-cell"><div class="player-avatar av-${p.pos}" style="${p.doubt?'opacity:0.55;':''}"><b>${p.pos}</b></div><div><span class="player-name" style="${p.doubt?'color:#92400e;':''}">${p.name}</span>${penBadge}${spBadge}${formBadge}${doubtBadge}${consDot}<br><span class="club-tag">${p.club}</span>${xsvLine}</div></div></td>
      <td><span class="pos-badge pos-${p.pos}">${POS_LABELS[p.pos]||p.pos}</span><br><span class="role-badge role-${roleLabel}">${roleLabel}</span></td>
      <td><span class="fdr-chip ${fdrCls}" style="font-size:10px;padding:2px 6px;" title="${fdrTip}">${p.opp.split(" ")[0]} · FDR${p.fdr_opp}</span><br>${lvTag}</td>
      <td><span class="xpts-val" style="cursor:help;" title="${bkTitle}">${p.xpts}</span></td>
      <td style="color:${p.xpts_per_m!=null?(p.xpts_per_m>=0.8?'#10b981':p.xpts_per_m>=0.55?'#f59e0b':'#94a3b8'):'#cbd5e1'};font-weight:700;" title="${p.fm_price?'Precio FM: $'+p.fm_price+'M':'Sin precio FM'}">${p.xpts_per_m!=null?p.xpts_per_m.toFixed(2):'—'}</td>
      <td style="color:#7c3aed;font-weight:700;">${p.cap_score!=null?p.cap_score.toFixed(2):"—"}</td>
      <td style="color:${p.p_play>=0.85?'#10b981':p.p_play>=0.60?'#f59e0b':'#ef4444'};font-weight:700;">${p.p_play!=null?Math.round(p.p_play*100)+'%':"—"}</td>
      <td>${probBar(p.p_goal,"fill-goal")}</td>
      <td>${probBar(p.p_assist,"fill-assist")}</td>
      <td>${probBar(p.p_cs,"fill-cs")}</td>
      <td style="color:#475569;">${p.xg_90}</td>
      <td style="color:#475569;">${p.npxg_90!=null?p.npxg_90:"—"}</td>
      <td style="color:#475569;">${p.xa_90}</td>
      <td style="color:#475569;">${p.xgi_90!=null?p.xgi_90:"—"}</td>
      <td style="color:#475569;">${p.sca_90!=null?p.sca_90.toFixed(2):"—"}</td>
      <td style="color:#475569;">${p.gca_90!=null?p.gca_90.toFixed(2):"—"}</td>
      <td style="color:#475569;">${p.prog_carries_90!=null?p.prog_carries_90.toFixed(2):"—"}</td>
      <td style="color:${p.style_match==null||p.style_match===0?'#cbd5e1':p.style_match>3?'#10b981':p.style_match>0?'#34d399':p.style_match<-3?'#ef4444':'#fca5a5'};font-weight:700;text-align:center;" title="${p.player_type||''}">${p.style_match!=null&&p.style_match!==0?(p.style_match>0?'+':'')+p.style_match.toFixed(1)+'%':'—'}</td>
      <td style="color:${p.bpr_rate>20?'#f59e0b':p.bpr_rate>0?'#64748b':'#cbd5e1'};font-weight:700;">${p.bpr_rate>0?p.bpr_rate.toFixed(0)+'%':'—'}</td>
      <td style="color:#0f172a;">${p.goals}</td>
      <td style="color:#0f172a;">${p.assists}</td>
      <td style="color:${p.xg_over==null?'#cbd5e1':p.xg_over>0.5?'#f97316':p.xg_over<-0.5?'#1a56db':'#64748b'};font-weight:700;">${p.xg_over!=null?(p.xg_over>0?'+':'')+p.xg_over.toFixed(2):'—'}</td>
      <td style="color:${ratingColor};font-weight:700;" data-tip="Rating promedio de temporada SofaScore. No refleja rendimiento en este partido específico.">${ratingStr}</td>
      <td style="color:${p.form_rating!=null?(p.form_rating>=7.5?'#10b981':p.form_rating>=6.5?'#f59e0b':'#ef4444'):'#cbd5e1'};font-weight:700;">${p.form_rating!=null?p.form_rating.toFixed(2):'—'}</td>
      <td style="color:${p.fm_mean_pts!=null?(p.fm_mean_pts>=6?'#10b981':p.fm_mean_pts>=4.5?'#f59e0b':'#64748b'):'#cbd5e1'};font-weight:700;">${p.fm_mean_pts!=null?p.fm_mean_pts.toFixed(1):'—'}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById("row-count").textContent = `${rows.length} jugadores mostrados de ${D.players.length} en fixtures confirmados`;

  // Update sort headers
  document.querySelectorAll("#player-table th").forEach(th=>{
    th.classList.remove("sort-asc","sort-desc");
    if(th.dataset.col===currentSort) th.classList.add(sortDir==="desc"?"sort-desc":"sort-asc");
  });
}

// Position tabs
document.getElementById("pos-tabs").querySelectorAll(".tab").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.getElementById("pos-tabs").querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    currentPos = btn.dataset.pos;
    renderPlayerTable();
  });
});

// Sort header clicks
document.querySelectorAll("#player-table th").forEach(th=>{
  th.addEventListener("click",()=>{
    const col = th.dataset.col;
    if(currentSort===col) sortDir = sortDir==="desc"?"asc":"desc";
    else{ currentSort=col; sortDir="desc"; }
    renderPlayerTable();
  });
});

// Search
document.getElementById("search-input").addEventListener("input",e=>{
  searchQ = e.target.value.trim();
  renderPlayerTable();
});

// Sort select
document.getElementById("sort-select").addEventListener("change",e=>{
  currentSort = e.target.value;
  sortDir = "desc";
  renderPlayerTable();
});

// ── FDR Grid ───────────────────────────────────────────────────────────────
function renderFDRGrid(){
  const grid = document.getElementById("fdr-grid");
  grid.innerHTML = "";
  D.fdr_table.forEach(t=>{
    const fdr = t.fdr;
    const fdrColors = {
      1:{bg:"#00c853",txt:"#fff"},
      2:{bg:"#69f0ae",txt:"#064e3b"},
      3:{bg:"#fff9c4",txt:"#78350f"},
      4:{bg:"#ff9800",txt:"#fff"},
      5:{bg:"#f44336",txt:"#fff"}
    };
    const col = fdrColors[fdr]||fdrColors[3];
    const fillColor = col.txt;
    const prof = D.def_profiles && D.def_profiles[t.club];
    let vulnHtml = "";
    if(prof && prof.vuln_label){
      vulnHtml = `<div class="fdr-vuln">↑ vulnerable a: ${prof.vuln_label}</div>`;
    }
    const card = document.createElement("div");
    card.className = "fdr-row-card";
    card.innerHTML = `
      <div class="fdr-badge-big" style="background:${col.bg};color:${col.txt};">${fdr}</div>
      <div class="fdr-info">
        <div class="fdr-club" title="${t.club}">${t.club}</div>
        <div class="fdr-stats" title="gc/pj: goles concedidos reales por partido | xgc/pj: expected goals concedidos por partido (mejor indicador de calidad defensiva, elimina la varianza del arquero) | VI: % de vallas invictas | def: score defensivo 0-100 usado para el FDR">${t.gc_pg} gc/pj · ${t.xgc_pg||t.gc_pg} xgc/pj · ${t.vi_pct}% VI · def ${t.def_score}</div>
        <div class="fdr-score-bar"><div class="fdr-score-fill" style="width:${t.def_score}%;background:${fillColor};"></div></div>
        ${vulnHtml}
      </div>`;
    grid.appendChild(card);
  });
}

// ── Simulator ─────────────────────────────────────────────────────────────
let simPos = "ALL";

function populateSimSelects(){
  const clubs = D.all_clubs;
  ["sim-home","sim-away"].forEach((id,i)=>{
    const sel = document.getElementById(id);
    sel.innerHTML = "";
    clubs.forEach(c=>{
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      if(i===0 && c==="River Plate") opt.selected=true;
      if(i===1 && c==="San Lorenzo") opt.selected=true;
      sel.appendChild(opt);
    });
  });
}

function calcSimProjection(p, oppClub, isHome){
  const opp = D.team_stats[oppClub]||{def_score:50,att_score:50,fdr:3};
  const own  = D.team_stats[p.club]||{def_score:50,att_score:50};
  const oppDef = opp.def_score||50;
  const oppAtt = opp.att_score||50;
  const ownDef = own.def_score||50;

  const defMult  = 1.0 + (50-oppDef)/100;
  const homeMult = isHome ? 1.12 : 0.88;
  const minsFac  = p.mins_fac||1.0;

  const GOAL_POS   = {G:0.004,D:0.055,M:0.44,F:0.85};
  const ASSIST_POS = {G:0.004,D:0.11, M:0.60,F:0.38};

  const xgReg   = p.xg_90_reg != null ? p.xg_90_reg : p.xg_90;
  const xaReg   = p.xa_90_reg != null ? p.xa_90_reg : p.xa_90;
  const pGoal   = Math.min(0.70, xgReg * defMult * homeMult * (GOAL_POS[p.pos]||0.3) * minsFac);
  const pAssist = Math.min(0.55, xaReg * defMult * homeMult * (ASSIST_POS[p.pos]||0.3) * minsFac);
  const csRaw   = (ownDef - oppAtt + 100)/200;
  const pCs     = Math.min(0.72, Math.max(0.03, csRaw * (isHome?1.15:0.85)));

  const GOAL_PTS = {G:8,D:8,M:5,F:4};
  const CS_PTS   = {G:5,D:4,M:1,F:0};
  const cardPen  = (p.amarillas / Math.max(p.games,1)) * -1;
  const xpts = pGoal*(GOAL_PTS[p.pos]||4) + pAssist*3 + pCs*(CS_PTS[p.pos]||0) + minsFac*2 + cardPen;

  return {
    p_goal:   Math.round(pGoal*1000)/10,
    p_assist: Math.round(pAssist*1000)/10,
    p_cs:     Math.round(pCs*1000)/10,
    xpts:     Math.round(xpts*100)/100,
    fdr_opp:  opp.fdr||3,
  };
}

function runSimulator(){
  const homeClub = document.getElementById("sim-home").value;
  const awayClub = document.getElementById("sim-away").value;
  if(homeClub===awayClub){ alert("El local y visitante no pueden ser el mismo equipo."); return; }

  const results = [];
  D.sim_players.forEach(p=>{
    let isHome=null, opp=null;
    if(p.club===homeClub){ isHome=true;  opp=awayClub; }
    if(p.club===awayClub){ isHome=false; opp=homeClub; }
    if(opp===null) return;
    if(simPos!=="ALL" && p.pos!==simPos) return;

    const proj = calcSimProjection(p, opp, isHome);
    results.push({...p, ...proj, is_home:isHome, opp});
  });

  results.sort((a,b)=>b.xpts-a.xpts);

  const tbody = document.getElementById("sim-tbody");
  tbody.innerHTML = "";
  results.slice(0,40).forEach(p=>{
    const tr = document.createElement("tr");
    const fdrCls = FDR_COLORS[p.fdr_opp]||"fdr-3";
    const lv = p.is_home?`<span class="home-tag">🏠</span>`:`<span class="away-tag">✈</span>`;
    tr.innerHTML = `
      <td><span class="player-name">${p.name}</span></td>
      <td><span class="club-tag">${p.club}</span></td>
      <td><span class="pos-badge pos-${p.pos}">${p.pos}</span></td>
      <td>${lv}</td>
      <td><span class="xpts-val">${p.xpts}</span></td>
      <td>${probBar(p.p_goal,"fill-goal")}</td>
      <td>${probBar(p.p_assist,"fill-assist")}</td>
      <td>${probBar(p.p_cs,"fill-cs")}</td>
      <td style="color:#94a3b8;">${p.xg_90.toFixed(3)}</td>`;
    tbody.appendChild(tr);
  });

  const hd = D.team_stats[homeClub]||{};
  const ad = D.team_stats[awayClub]||{};
  document.getElementById("sim-fdr-preview").textContent =
    `${homeClub.split(" ")[0]} enfrenta FDR ${ad.fdr||"?"} · ${awayClub.split(" ")[0]} enfrenta FDR ${hd.fdr||"?"}`;

  document.getElementById("sim-results").style.display = "block";
}

document.getElementById("sim-run-btn").addEventListener("click", runSimulator);

document.getElementById("sim-pos-tabs").querySelectorAll(".tab").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.getElementById("sim-pos-tabs").querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    simPos = btn.dataset.pos;
    runSimulator();
  });
});

// ── INIT ──────────────────────────────────────────────────────────────────
renderTopPicks();
renderFixtures();
renderPlayerTable();
renderFDRGrid();
populateSimSelects();
</script>
</body>
</html>"""

# Inyectar datos y leaders bar
HTML = HTML.replace("/*__DATA__*/", data_json, 1)
HTML = HTML.replace("/*__LEADERS__*/", leaders_html, 1)
HTML = HTML.replace("/*__CAPTAIN__*/", captain_html, 1)
HTML = HTML.replace("/*__DT__*/",      dt_html,      1)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(HTML)

size_kb = os.path.getsize(OUT_PATH) / 1024
print(f"analytics.html generado: {size_kb:.0f} KB")
print(f"Jugadores en fixtures confirmados: {len(player_list)}")
print(f"Equipos en FDR table: {len(fdr_table)}")
print(f"Jugadores en simulador: {len(sim_players)}")
print("\nTop 10 xPts:")
for p in player_list[:10]:
    print(f"  {p['xpts']:5.2f} xPts | {p['name']:<25} ({p['club']}) vs {p['opp']} FDR{p['fdr_opp']}")

# ── Reporte de ajustes automáticos de rol ─────────────────────────────────
if _role_change_log:
    print("\n[role-change discount aplicado - xG/90 x0.80 por cambio suplente->titular]")
    for line in _role_change_log:
        print(line)

# ── Chequeo: suplentes/rotacionales con xG/90 alto sin override ──────────
# Avisa si hay candidatos que podrían necesitar ajuste manual de titularidad.
_warn_threshold = 0.25
_warn_players = [
    p for p in player_list
    if p.get("role") in ("Suplente", "Rotacional")
    and (p.get("xg_90") or 0) > _warn_threshold
    and p.get("pos") in ("M", "F")
]
if _warn_players:
    print(f"\n[REVISAR] Suplentes/Rotacionales con xG/90 > {_warn_threshold} — confirmar titularidad:")
    print(f"  {'Jugador':<28} {'Club':<8} Pos  avg_m  xG/90   Rol")
    for p in sorted(_warn_players, key=lambda x: x.get("xg_90", 0), reverse=True):
        mins  = p.get("mins", 0)
        games = p.get("games", 1)
        avg_m = mins / max(games, 1)
        print(f"  {p['name'][:28]:<28} {p['club'][:8]:<8}  {p['pos']}  {avg_m:>5.1f}  {p.get('xg_90',0):.3f}  {p['role']}")
