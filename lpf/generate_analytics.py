#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LPF Fantasy Analytics — Generador
Apertura 2026 | Análisis probabilístico para Fantasy Manager Argentina
Metodología inspirada en Opta / FPL Review
"""

import json, math, os

JSON_PATH = r"c:/Users/Franco/DashBoards Futbol/lpf/lpf_data.json"
OUT_PATH  = r"c:/Users/Franco/DashBoards Futbol/lpf/analytics.html"

# ── Scoring Fantasy Manager Argentina ─────────────────────────────────────
FM = {
    "goal":   {"G": 8, "D": 6, "M": 5, "F": 4},
    "assist": 3,
    "cs":     {"G": 5, "D": 4, "M": 1, "F": 0},
    "mins":   2,      # jugó >60 min
    "yellow": -1,
    "red":    -3,
}

# ── Fixtures confirmados Octavos de Final Apertura 2026 ───────────────────
FIXTURES = [
    {"id": 1, "home": "Estudiantes de La Plata",  "away": "Barracas Central",   "round": "Octavos — Ida"},
    {"id": 2, "home": "Vélez Sarsfield",           "away": "Gimnasia y Esgrima", "round": "Octavos — Ida"},
    {"id": 3, "home": "River Plate",               "away": "San Lorenzo",        "round": "Octavos — Ida"},
    {"id": 4, "home": "Rosario Central",           "away": "CA Independiente",   "round": "Octavos — Ida"},
]

# ── Cargar datos ───────────────────────────────────────────────────────────
with open(JSON_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)

players_raw = raw["Primera LPF 2026"]

# ── STEP 1: Stats por equipo ───────────────────────────────────────────────
def get_team_stats(players):
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

        # Defense score 0–100: menor gc + mayor VI = más fuerte
        gc_norm = max(0.0, min(100.0, 100 - (gc_pg - 0.4) * 52))
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
            "vi_pct":   round(vi_rate * 100, 1),
            "xg_pg":    round(xg_pg, 2),
            "gf_pg":    round(gf_pg, 2),
            "def_score": def_score,
            "att_score": att_score,
            "fdr":       fdr,
        }
    return result

team_stats = get_team_stats(players_raw)

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

    opp  = ts.get(opp_club, {"def_score": 50, "att_score": 50, "fdr": 3})
    own  = ts.get(p["Club"],   {"def_score": 50, "att_score": 50})

    opp_def = opp["def_score"]
    opp_att = opp["att_score"]
    own_def = own["def_score"]

    # Multiplicadores
    def_mult  = 1.0 + (50 - opp_def) / 100          # 0.5–1.5
    home_mult = 1.12 if is_home else 0.88
    avg_mins  = mins / games
    mins_fac  = min(1.0, avg_mins / 90)

    # Multiplicadores por posición (calibrados para p_goal razonable)
    GOAL_POS   = {"G": 0.004, "D": 0.055, "M": 0.44, "F": 0.85}
    ASSIST_POS = {"G": 0.004, "D": 0.11,  "M": 0.60, "F": 0.38}

    p_goal   = min(0.70, xg_90 * def_mult * home_mult * GOAL_POS.get(pos, 0.3) * mins_fac)
    p_assist = min(0.55, xa_90 * def_mult * home_mult * ASSIST_POS.get(pos, 0.3) * mins_fac)

    # Clean sheet: defensa propia vs ataque rival
    cs_raw   = (own_def - opp_att + 100) / 200        # 0.0–1.0
    cs_home  = 1.15 if is_home else 0.85
    p_cs     = min(0.72, max(0.03, cs_raw * cs_home))

    # xPts Fantasy Manager
    yellows  = p.get("Amarillas") or 0
    card_pen = (yellows / games) * FM["yellow"]

    xpts = (
        p_goal   * FM["goal"].get(pos, 4) +
        p_assist * FM["assist"] +
        p_cs     * FM["cs"].get(pos, 0) +
        mins_fac * FM["mins"] +
        card_pen
    )

    return {
        "p_goal":   round(p_goal   * 100, 1),
        "p_assist": round(p_assist * 100, 1),
        "p_cs":     round(p_cs     * 100, 1),
        "xg_90":    round(xg_90, 3),
        "xa_90":    round(xa_90, 3),
        "fdr_opp":  opp["fdr"],
        "xpts":     round(xpts, 2),
        "mins_fac": round(mins_fac, 2),
    }

# ── STEP 3: Armar dataset de jugadores ────────────────────────────────────
fixture_map = {}   # club → (rival, is_home)
for fx in FIXTURES:
    fixture_map[fx["home"]] = (fx["away"], True)
    fixture_map[fx["away"]] = (fx["home"], False)

player_list = []
for p in players_raw:
    club = p.get("Club")
    pos  = p.get("Posicion")
    mins = p.get("Minutos Jugados") or 0
    if mins < 90 or not pos or club not in fixture_map:
        continue

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

    sim_players.append({
        "name":        p["Jugador"],
        "club":        p["Club"],
        "pos":         pos,
        "mins_fac":    round(min(1.0, (mins / games) / 90), 2),
        "xg_90":       round(xg_90, 4),
        "xa_90":       round(xa_90, 4),
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

# ── Serializar datos para el HTML ─────────────────────────────────────────
DATA = {
    "fixtures":    FIXTURES,
    "players":     player_list,
    "team_stats":  team_stats,
    "fdr_table":   fdr_table,
    "sim_players": sim_players,
    "all_clubs":   sorted(team_stats.keys()),
    "fm_scoring":  FM,
}

data_json = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))

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
body{background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0;min-width:320px;}

/* ── HEADER ── */
#header{background:linear-gradient(135deg,#0d1b35 0%,#0a0e1a 100%);border-bottom:2px solid #00d4f5;padding:18px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;}
.header-left{display:flex;align-items:center;gap:14px;}
.badge-lpf{background:#00d4f5;color:#0a0e1a;font-weight:800;font-size:11px;padding:4px 10px;border-radius:4px;letter-spacing:.6px;}
.header-title h1{font-size:22px;font-weight:700;color:#fff;}
.header-title p{font-size:12px;color:#7891b5;margin-top:2px;}
.header-meta{text-align:right;font-size:11px;color:#5a7090;}
.header-meta span{color:#ffc107;font-weight:600;}

/* ── MAIN ── */
#main{max-width:1300px;margin:0 auto;padding:24px 20px 60px;}

/* ── SECTION TITLE ── */
.sec-title{font-size:13px;font-weight:700;color:#00d4f5;letter-spacing:.5px;text-transform:uppercase;border-left:3px solid #00d4f5;padding-left:10px;margin-bottom:16px;}

/* ── FIXTURE CARDS ── */
#fixtures-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:32px;}
.fx-card{background:#111827;border:1px solid #1e2d44;border-radius:10px;padding:16px 18px;}
.fx-round{font-size:10px;font-weight:700;color:#7891b5;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px;}
.fx-matchup{display:flex;align-items:center;justify-content:space-between;gap:8px;}
.fx-team{flex:1;}
.fx-team-name{font-size:13px;font-weight:700;color:#e2e8f0;line-height:1.2;}
.fx-team-tag{font-size:10px;color:#7891b5;margin-top:2px;}
.fx-vs{font-size:11px;font-weight:700;color:#5a7090;padding:0 4px;}
.fx-fdr-row{display:flex;gap:8px;margin-top:12px;}
.fdr-chip{flex:1;text-align:center;padding:5px 4px;border-radius:6px;font-size:11px;font-weight:700;}
.fdr-1{background:#1a4a2e;color:#4ade80;}
.fdr-2{background:#1e3a1e;color:#86efac;}
.fdr-3{background:#3b2f00;color:#fbbf24;}
.fdr-4{background:#3b1a00;color:#fb923c;}
.fdr-5{background:#3b0a0a;color:#f87171;}

/* ── TABS ── */
.tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap;}
.tab{background:#111827;border:1px solid #1e2d44;color:#7891b5;font-size:12px;font-weight:600;padding:7px 16px;border-radius:20px;cursor:pointer;transition:all .15s;}
.tab:hover{border-color:#00d4f5;color:#00d4f5;}
.tab.active{background:#00d4f5;color:#0a0e1a;border-color:#00d4f5;}

/* ── PLAYER TABLE ── */
.search-row{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;align-items:center;}
#search-input{flex:1;min-width:180px;background:#111827;border:1px solid #1e2d44;color:#e2e8f0;padding:8px 12px;border-radius:7px;font-size:13px;outline:none;}
#search-input:focus{border-color:#00d4f5;}
.sort-select{background:#111827;border:1px solid #1e2d44;color:#7891b5;padding:7px 10px;border-radius:7px;font-size:12px;cursor:pointer;outline:none;}
.sort-select:focus{border-color:#00d4f5;}

.tbl-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:12.5px;min-width:700px;}
thead th{background:#0d1421;color:#7891b5;padding:9px 10px;text-align:left;font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;white-space:nowrap;cursor:pointer;user-select:none;}
thead th:hover{color:#00d4f5;}
thead th.sort-asc::after{content:" ▲";font-size:8px;}
thead th.sort-desc::after{content:" ▼";font-size:8px;}
tbody tr{border-bottom:1px solid #111827;}
tbody tr:hover{background:#111827;}
td{padding:8px 10px;white-space:nowrap;vertical-align:middle;}
.player-name{font-weight:600;color:#e2e8f0;}
.club-tag{font-size:11px;color:#7891b5;}
.pos-badge{display:inline-block;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700;}
.pos-G{background:#1a3050;color:#60a5fa;}
.pos-D{background:#1a3a1e;color:#4ade80;}
.pos-M{background:#3b2f00;color:#fbbf24;}
.pos-F{background:#3b0e10;color:#f87171;}
.home-tag{background:#1a3050;color:#60a5fa;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;}
.away-tag{background:#1e2d44;color:#94a3b8;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;}

/* ── PROB BARS ── */
.prob-cell{min-width:90px;}
.prob-bar-wrap{display:flex;align-items:center;gap:6px;}
.prob-val{font-size:11px;font-weight:700;min-width:34px;text-align:right;}
.prob-bar{flex:1;height:5px;background:#1e2d44;border-radius:3px;overflow:hidden;}
.prob-fill{height:100%;border-radius:3px;}
.fill-goal{background:#f87171;}
.fill-assist{background:#60a5fa;}
.fill-cs{background:#4ade80;}
.xpts-val{font-size:14px;font-weight:800;color:#ffc107;}

/* ── FDR TABLE ── */
#fdr-section{margin-top:36px;}
.fdr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;}
.fdr-row-card{background:#111827;border:1px solid #1e2d44;border-radius:8px;padding:12px 14px;display:flex;align-items:center;gap:12px;}
.fdr-badge-big{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:900;flex-shrink:0;}
.fdr-info{flex:1;min-width:0;}
.fdr-club{font-size:12px;font-weight:700;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fdr-stats{font-size:10.5px;color:#7891b5;margin-top:2px;}
.fdr-score-bar{height:3px;border-radius:2px;margin-top:5px;background:#1e2d44;overflow:hidden;}
.fdr-score-fill{height:100%;border-radius:2px;}

/* ── SIMULATOR ── */
#sim-section{margin-top:36px;}
.sim-controls{background:#111827;border:1px solid #1e2d44;border-radius:10px;padding:18px 20px;margin-bottom:20px;}
.sim-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.sim-label{font-size:12px;font-weight:600;color:#7891b5;min-width:70px;}
.sim-select{background:#0d1421;border:1px solid #1e2d44;color:#e2e8f0;padding:8px 12px;border-radius:7px;font-size:13px;cursor:pointer;outline:none;min-width:200px;}
.sim-select:focus{border-color:#00d4f5;}
.sim-toggle{display:flex;gap:6px;}
.sim-toggle button{background:#0d1421;border:1px solid #1e2d44;color:#7891b5;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;}
.sim-toggle button.active{background:#00d4f5;color:#0a0e1a;border-color:#00d4f5;}
#sim-run-btn{background:#00d4f5;color:#0a0e1a;border:none;padding:9px 20px;border-radius:7px;font-size:13px;font-weight:700;cursor:pointer;}
#sim-run-btn:hover{background:#00bce0;}
#sim-results{display:none;}
.sim-top-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:16px;}
.sim-player-card{background:#0d1421;border:1px solid #1e2d44;border-radius:8px;padding:12px 14px;}
.sim-player-name{font-size:13px;font-weight:700;color:#e2e8f0;margin-bottom:2px;}
.sim-player-sub{font-size:11px;color:#7891b5;margin-bottom:8px;}
.sim-probs{display:flex;flex-direction:column;gap:4px;}
.sim-prob-row{display:flex;justify-content:space-between;font-size:11px;}
.sim-prob-label{color:#7891b5;}
.sim-prob-val{font-weight:700;}

/* ── METHODOLOGY ── */
#method-section{margin-top:40px;background:#111827;border:1px solid #1e2d44;border-radius:10px;padding:22px 24px;}
#method-section h3{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:14px;}
.method-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;}
.method-card{background:#0d1421;border-radius:8px;padding:14px 16px;}
.method-card h4{font-size:12px;font-weight:700;color:#00d4f5;margin-bottom:6px;}
.method-card p{font-size:11.5px;color:#94a3b8;line-height:1.5;}
.method-formula{background:#0a0e1a;border-left:3px solid #00d4f5;padding:8px 12px;border-radius:0 6px 6px 0;margin-top:8px;font-family:monospace;font-size:11px;color:#7891b5;}

/* ── FOOTER ── */
#footer{background:#0d1421;border-top:1px solid #1e2d44;padding:16px 28px;text-align:center;font-size:11px;color:#5a7090;margin-top:10px;}
#footer a{color:#00d4f5;text-decoration:none;}

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
    <a href="https://github.com" style="color:#00d4f5;font-size:11px;">Ver en GitHub</a>
  </div>
</div>

<div id="main">

  <!-- FIXTURES -->
  <div style="margin-bottom:8px;">
    <div class="sec-title">Octavos de Final — Próximos fixtures</div>
    <div id="fixtures-grid"></div>
  </div>

  <!-- PLAYER PROJECTIONS -->
  <div style="margin-top:28px;">
    <div class="sec-title">Proyecciones por jugador</div>
    <p style="font-size:11.5px;color:#5a7090;margin-bottom:14px;">
      xPts calculado con metodología Opta: xG/90 × debilidad defensiva del rival × ventaja de local/visitante × multiplicador de posición.
      Puntuación: gol ARQ 8pts / DEF 6pts / MED 5pts / DEL 4pts · asistencia 3pts · valla invicta ARQ 5pts / DEF 4pts / MED 1pt.
    </p>

    <div class="tabs" id="pos-tabs">
      <button class="tab active" data-pos="ALL">Todos</button>
      <button class="tab" data-pos="G">Arqueros</button>
      <button class="tab" data-pos="D">Defensores</button>
      <button class="tab" data-pos="M">Mediocampistas</button>
      <button class="tab" data-pos="F">Delanteros</button>
    </div>

    <div class="search-row">
      <input id="search-input" type="text" placeholder="Buscar jugador o club..."/>
      <select class="sort-select" id="sort-select">
        <option value="xpts">Ordenar: xPts</option>
        <option value="p_goal">Ordenar: P(Gol)</option>
        <option value="p_assist">Ordenar: P(Asistencia)</option>
        <option value="p_cs">Ordenar: P(Valla Invicta)</option>
        <option value="xg_90">Ordenar: xG/90</option>
        <option value="rating">Ordenar: Rating</option>
      </select>
    </div>

    <div class="tbl-wrap">
      <table id="player-table">
        <thead>
          <tr>
            <th data-col="name">Jugador</th>
            <th data-col="pos">Pos</th>
            <th data-col="opp">Rival</th>
            <th data-col="xpts" class="sort-desc">xPts ↓</th>
            <th data-col="p_goal">P(Gol)</th>
            <th data-col="p_assist">P(Asist)</th>
            <th data-col="p_cs">P(VI)</th>
            <th data-col="xg_90">xG/90</th>
            <th data-col="xa_90">xA/90</th>
            <th data-col="goals">G</th>
            <th data-col="assists">A</th>
            <th data-col="rating">Rating</th>
          </tr>
        </thead>
        <tbody id="player-tbody"></tbody>
      </table>
    </div>
    <p id="row-count" style="font-size:11px;color:#5a7090;margin-top:8px;"></p>
  </div>

  <!-- FDR TABLE -->
  <div id="fdr-section">
    <div class="sec-title">Índice de dificultad de fixture (FDR) — todos los equipos</div>
    <p style="font-size:11.5px;color:#5a7090;margin-bottom:14px;">
      FDR 1 (verde) = defensa débil, fixture fácil para atacantes. FDR 5 (rojo) = defensa sólida, fixture muy difícil.
      Calculado con: goles concedidos/partido (65%) + tasa de vallas invictas (35%).
    </p>
    <div class="fdr-grid" id="fdr-grid"></div>
  </div>

  <!-- SIMULATOR -->
  <div id="sim-section">
    <div class="sec-title">Simulador de fixture</div>
    <p style="font-size:11.5px;color:#5a7090;margin-bottom:14px;">
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
  &nbsp;·&nbsp; <strong style="color:#e2e8f0;">No reemplaza análisis profesional · Uso informativo</strong>
</div>

<script>
const D = /*__DATA__*/;

const FDR_COLORS = {1:"fdr-1",2:"fdr-2",3:"fdr-3",4:"fdr-4",5:"fdr-5"};
const FDR_LABELS = {1:"FDR 1 · Fácil",2:"FDR 2 · Accesible",3:"FDR 3 · Medio",4:"FDR 4 · Difícil",5:"FDR 5 · Muy difícil"};
const POS_LABELS = {G:"Arquero",D:"Defensor",M:"Mediocampista",F:"Delantero"};

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
      <div class="fx-round">${fx.round}</div>
      <div class="fx-matchup">
        <div class="fx-team">
          <div class="fx-team-name">${fx.home}</div>
          <div class="fx-team-tag">Local</div>
        </div>
        <div class="fx-vs">vs</div>
        <div class="fx-team" style="text-align:right">
          <div class="fx-team-name">${fx.away}</div>
          <div class="fx-team-tag">Visitante</div>
        </div>
      </div>
      <div class="fx-fdr-row">
        <div class="fdr-chip ${FDR_COLORS[aFdr]}" title="FDR que enfrenta ${fx.home}">${fx.home.split(" ")[0]} enfrenta FDR ${aFdr}</div>
        <div class="fdr-chip ${FDR_COLORS[hFdr]}" title="FDR que enfrenta ${fx.away}">${fx.away.split(" ")[0]} enfrenta FDR ${hFdr}</div>
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
let currentSort = "xpts";
let sortDir     = "desc";
let searchQ     = "";

function filteredPlayers(){
  return D.players.filter(p=>{
    if(currentPos !== "ALL" && p.pos !== currentPos) return false;
    const q = searchQ.toLowerCase();
    if(q && !p.name.toLowerCase().includes(q) && !p.club.toLowerCase().includes(q)) return false;
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
    const ratingColor = p.rating>=7.5?"#4ade80":p.rating>=6.5?"#fbbf24":"#f87171";
    const fdrCls = FDR_COLORS[p.fdr_opp]||"fdr-3";
    const lvTag = p.is_home
      ?`<span class="home-tag">🏠 Local</span>`
      :`<span class="away-tag">✈ Visit.</span>`;
    tr.innerHTML = `
      <td><span class="player-name">${p.name}</span><br><span class="club-tag">${p.club}</span></td>
      <td><span class="pos-badge pos-${p.pos}">${POS_LABELS[p.pos]||p.pos}</span></td>
      <td><span class="fdr-chip ${fdrCls}" style="font-size:10px;padding:2px 6px;">${p.opp.split(" ")[0]} · FDR${p.fdr_opp}</span><br>${lvTag}</td>
      <td><span class="xpts-val">${p.xpts}</span></td>
      <td>${probBar(p.p_goal,"fill-goal")}</td>
      <td>${probBar(p.p_assist,"fill-assist")}</td>
      <td>${probBar(p.p_cs,"fill-cs")}</td>
      <td style="color:#94a3b8;">${p.xg_90}</td>
      <td style="color:#94a3b8;">${p.xa_90}</td>
      <td>${p.goals}</td>
      <td>${p.assists}</td>
      <td style="color:${ratingColor};font-weight:700;">${ratingStr}</td>`;
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
      1:{bg:"#1a4a2e",txt:"#4ade80"},
      2:{bg:"#1e3a1e",txt:"#86efac"},
      3:{bg:"#3b2f00",txt:"#fbbf24"},
      4:{bg:"#3b1a00",txt:"#fb923c"},
      5:{bg:"#3b0a0a",txt:"#f87171"}
    };
    const col = fdrColors[fdr]||fdrColors[3];
    const fillColor = col.txt;
    const card = document.createElement("div");
    card.className = "fdr-row-card";
    card.innerHTML = `
      <div class="fdr-badge-big" style="background:${col.bg};color:${col.txt};">${fdr}</div>
      <div class="fdr-info">
        <div class="fdr-club" title="${t.club}">${t.club}</div>
        <div class="fdr-stats">${t.gc_pg} gc/pj · ${t.vi_pct}% VI · def ${t.def_score}</div>
        <div class="fdr-score-bar"><div class="fdr-score-fill" style="width:${t.def_score}%;background:${fillColor};"></div></div>
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

  const pGoal   = Math.min(0.70, p.xg_90 * defMult * homeMult * (GOAL_POS[p.pos]||0.3) * minsFac);
  const pAssist = Math.min(0.55, p.xa_90 * defMult * homeMult * (ASSIST_POS[p.pos]||0.3) * minsFac);
  const csRaw   = (ownDef - oppAtt + 100)/200;
  const pCs     = Math.min(0.72, Math.max(0.03, csRaw * (isHome?1.15:0.85)));

  const GOAL_PTS = {G:8,D:6,M:5,F:4};
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
renderFixtures();
renderPlayerTable();
renderFDRGrid();
populateSimSelects();
</script>
</body>
</html>"""

# Inyectar datos
HTML = HTML.replace("/*__DATA__*/", data_json, 1)

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
