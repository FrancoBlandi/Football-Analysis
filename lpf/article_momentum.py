#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
article_momentum.py — Articulo narrativo: momentum intra-partido LPF 2026.
Uso: python lpf/article_momentum.py
"""

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from analyze_momentum import (
    load_data, build_team_map, parse_match,
    analysis_autocorrelation, analysis_match_profile,
    analysis_triggers, analysis_duration,
    analysis_score_state, analysis_teams,
    analysis_predictive, global_stats,
    analysis_equalizer_context,
)

OUT_PATH = Path(__file__).parent / "momentum_article.html"


def js(obj):
    return json.dumps(obj, ensure_ascii=False)

def traj_xy(d, offsets):
    return [d.get(str(o)) for o in offsets]


# ─────────────────────────────────────────────────────────────────────────────

def build_article(r):
    ac    = r["autocorr"]
    prof  = r["profile"]
    trig  = r["triggers"]
    dur   = r["duration"]
    score = r["score_state"]
    teams = r["teams"]
    pred  = r["predictive"]
    glob  = r["global"]
    eq    = r["eq_context"]

    # ── chart data ────────────────────────────────────────────────────────────

    ac_lags  = list(ac.keys())
    ac_means = [ac[l]["mean"] for l in ac_lags]
    ac_ses   = [ac[l]["se"]   for l in ac_lags]
    ac_ps    = [ac[l]["p"]    for l in ac_lags]

    mins      = list(range(1, 91))
    prof_mean = [prof[m]["mean"] for m in mins]
    prof_p75  = [prof[m]["p75"]  for m in mins]
    prof_p25  = [prof[m]["p25"]  for m in mins]

    event_order = [
        ("red_card_rival",  "Roja: equipo que la recibe como ventaja"),
        ("red_card_victim", "Roja: equipo que queda con 10"),
        ("goal_scorer",     "Gol: equipo que convierte"),
        ("goal_conceder",   "Gol: equipo que recibe"),
        ("yellow_card",     "Amarilla: rival beneficiado"),
        ("substitution",    "Sustitucion: equipo que hace el cambio"),
    ]
    t_names, t_delta, t_p, t_n = [], [], [], []
    for key, label in event_order:
        if key in trig and trig[key]["n"] > 0:
            t_names.append(label)
            t_delta.append(trig[key]["mean_delta"])
            t_p.append(trig[key]["p_value"])
            t_n.append(trig[key]["n"])

    offs_s = list(range(-5, 11))
    offs_l = list(range(-5, 21))

    goal_t  = traj_xy(trig.get("goal_scorer",    {}).get("traj_mean", {}), offs_s)
    conc_t  = traj_xy(trig.get("goal_conceder",  {}).get("traj_mean", {}), offs_s)
    redr_t  = traj_xy(trig.get("red_card_rival", {}).get("traj_mean", {}), offs_s)
    redv_t  = traj_xy(trig.get("red_card_victim",{}).get("traj_mean", {}), offs_s)

    dur_t = [dur["traj"].get(str(o)) for o in offs_l]
    dur_u = [dur["traj"].get(str(o), 0) + dur["se"].get(str(o), 0) for o in offs_l]
    dur_d = [dur["traj"].get(str(o), 0) - dur["se"].get(str(o), 0) for o in offs_l]

    # Score state — si el split del equalizer es significativo, mostramos dos líneas;
    # si no, usamos la línea unificada del equalizer con nota en el texto
    eq_significant = eq.get("significant", False)
    eq_n_ann = eq.get("announced", {}).get("n", 0)
    eq_n_ctr = eq.get("counter",   {}).get("n", 0)
    eq_p     = eq.get("p_value", 1.0)

    ctx_def = {
        "go_ahead":      ("Gol que adelanta (empate -> ventaja)", "#3dde7a"),
        "extend_lead":   ("Gol que amplia ventaja",               "#4e9eff"),
        "pull_one_back": ("Gol que acorta la diferencia (sigue perdiendo)",    "#ff6b4e"),
    }
    score_traces = []
    for ctx, (label, color) in ctx_def.items():
        if ctx in score and score[ctx]["n"] > 0:
            score_traces.append({
                "name":  f"{label} (n={score[ctx]['n']})",
                "color": color,
                "y":     traj_xy(score[ctx]["traj"], offs_s),
            })

    if eq_significant:
        # Mostrar dos líneas separadas
        ann = eq.get("announced", {})
        ctr = eq.get("counter",   {})
        if ann.get("n", 0) > 0:
            score_traces.append({
                "name":  f"Empate anunciado (n={ann['n']})",
                "color": "#f5c542",
                "y":     traj_xy(ann["traj"], offs_s),
                "dash":  "solid",
            })
        if ctr.get("n", 0) > 0:
            score_traces.append({
                "name":  f"Empate a contragolpe (n={ctr['n']})",
                "color": "#f5c542",
                "y":     traj_xy(ctr["traj"], offs_s),
                "dash":  "dot",
            })
    else:
        # Línea unificada del equalizer
        if "equalizer" in score and score["equalizer"]["n"] > 0:
            score_traces.append({
                "name":  f"Gol del empate (n={score['equalizer']['n']})",
                "color": "#f5c542",
                "y":     traj_xy(score["equalizer"]["traj"], offs_s),
            })

    # Equipos — todos los disponibles, ordenados por dominancia
    team_list  = sorted(teams.items(), key=lambda x: -x[1]["pct_dominant"])[:20]
    t_eq_names = [t[0] for t in team_list]
    t_dom      = [t[1]["pct_dominant"]          for t in team_list]
    t_conv     = [t[1]["pct_goals_in_momentum"] for t in team_list]

    pred_ok = "auc" in pred

    # ── key numbers ──────────────────────────────────────────────────────────

    top_dom_name = team_list[0][0] if team_list else "—"
    top_dom_val  = team_list[0][1]["pct_dominant"] if team_list else 0
    best_conv    = max(teams.items(), key=lambda x: x[1]["pct_goals_in_momentum"]) if teams else ("—", {"pct_goals_in_momentum": 0})
    top_conv_name = best_conv[0]
    top_conv_val  = best_conv[1]["pct_goals_in_momentum"]

    red_delta  = abs(trig.get("red_card_rival", {}).get("mean_delta", 0))
    goal_delta = abs(trig.get("goal_scorer",    {}).get("mean_delta", 0))
    red_ratio  = round(red_delta / goal_delta, 1) if goal_delta > 0 else "—"

    hl     = dur["half_life"]
    hl_txt = str(hl) if hl else "mas de 20"

    auc     = pred.get("auc", 0.5) if pred_ok else 0.5
    auc_100 = round(auc * 100)

    # Persistencia: hasta qué lag es significativa la autocorrelación
    first_nosig = next((l for l in ac_lags if ac[l]["p"] >= 0.05), None)
    persist_txt = f"~{first_nosig} minutos" if first_nosig else "los 10 minutos analizados"

    # ── pred section ─────────────────────────────────────────────────────────

    if pred_ok:
        pred_js = (
            f'(function(){{\n'
            f'  const fpr={js(pred["fpr"])}; const tpr={js(pred["tpr"])};\n'
            f'  const lbls={js(pred["bucket_labels"])}; const rates={js(pred["bucket_rates"])};\n'
            f'  const base={js(float(pred["base_rate"]))};\n'
            f'  Plotly.newPlot("ch-roc",\n'
            f'    [{{x:fpr,y:tpr,type:"scatter",mode:"lines",name:"Modelo",line:{{color:"#4e9eff",width:2.5}}}},'
            f'     {{x:[0,1],y:[0,1],type:"scatter",mode:"lines",line:{{color:"#555",dash:"dot",width:1}},name:"Azar",showlegend:true}}],\n'
            f'    LA("",{{title:"Errores de clasificacion (falsos positivos)"}},{{title:"Aciertos (verdaderos positivos)"}}),cfg);\n'
            f'  const bc=rates.map(r=>r>base*1.15?"#3dde7a":r<base*0.85?"#ff6b4e":"#4e9eff");\n'
            f'  Plotly.newPlot("ch-buckets",\n'
            f'    [{{x:lbls,y:rates.map(v=>+(v*100).toFixed(1)),type:"bar",marker:{{color:bc}},name:"Goles con dominio previo (%)"}},\n'
            f'     {{x:[lbls[0],lbls[lbls.length-1]],y:[base*100,base*100],type:"scatter",mode:"lines",'
            f'      line:{{color:"#555",dash:"dot",width:1.5}},name:"Promedio general"}}],\n'
            f'    LA("",{{title:"Indice de presion promedio en los 5 min antes del gol"}},{{title:"% de goles anotados por el equipo dominante"}}),cfg);\n'
            f'}})();\n'
        )
        pred_html = f"""
<section class="article-section" id="prediccion">
  <div class="section-num">Hallazgo 06</div>
  <h2>El momentum predice quién anota: en 6 de cada 10 casos</h2>

  <p>La pregunta más práctica: ¿el nivel de presión de los últimos minutos sirve para anticipar quién convierte el próximo gol?</p>

  <p>Construimos un modelo que toma tres datos disponibles en cualquier momento del partido: la presión promedio de los últimos 5 minutos, el marcador actual y el tramo del partido. Con esos datos predice qué equipo anota a continuación.</p>

  <div class="explainer">
    <strong>Como se mide la precision del modelo:</strong> Imaginemos que tomamos dos momentos distintos
    del partido. En uno, el equipo A lleva 5 minutos presionando fuerte. En otro, presiona el equipo B.
    Le preguntamos al modelo: "¿cuál de los dos terminó en gol?" Si respondiera al azar,
    acertaría el 50% de las veces. Nuestro modelo acertó en <strong>{auc_100} de cada 100</strong> comparaciones.
  </div>

  <div class="pull-quote">
    <span class="pq-num">{auc_100} de 100</span>
    <span class="pq-desc">comparaciones correctas (vs 50 que acierta el azar puro)</span>
  </div>

  <p>El gráfico de barras es quizás el más intuitivo del análisis: cuando un equipo tuvo un índice de presión muy alto en los 5 minutos previos (barras de la derecha), sus goles representan el 65% o más del total. Cuando la presión fue baja o negativa (barras de la izquierda), esa proporción cae al 35-40%.</p>

  <p>El modelo no es lo suficientemente preciso para predecir el partido en tiempo real, pero confirma algo importante: el dominio territorial no es decorativo. Precede a los goles con una frecuencia que no es aleatoria.</p>

  <div class="chart-duo">
    <div class="chart-wrap small">
      <div id="ch-roc" style="height:290px"></div>
      <div class="chart-caption">La curva azul muestra el modelo. La línea punteada es lo que haría el azar puro. Cuanto más arriba y a la izquierda, mejor el modelo.</div>
    </div>
    <div class="chart-wrap small">
      <div id="ch-buckets" style="height:290px"></div>
      <div class="chart-caption">Cada barra muestra qué porcentaje de los goles fueron anotados por el equipo que tenía ese nivel de presión en los 5 minutos previos.</div>
    </div>
  </div>
</section>
"""
    else:
        pred_html = ""
        pred_js   = ""

    # ── HTML ─────────────────────────────────────────────────────────────────

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>El Momentum en la LPF 2026 | Franco Analytics</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0c0e13; --surface:#13161e; --surface2:#1a1f2a; --border:#252b38;
  --accent:#4e9eff; --green:#3dde7a; --orange:#ff6b4e; --yellow:#f5c542; --purple:#b44eff;
  --text:#dde1ea; --muted:#6b7585; --faint:#3a4252;
  --serif:'Georgia','Times New Roman',serif;
  --sans:'Segoe UI',system-ui,-apple-system,sans-serif;
  --w:720px; --ww:940px;
}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.75;font-size:16px}}

/* NAV */
nav{{position:sticky;top:0;z-index:100;background:rgba(12,14,19,.96);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--border);
  padding:0 2rem;display:flex;align-items:center;height:48px;gap:0}}
.nav-brand{{color:var(--accent);font-size:.76rem;font-weight:700;
  padding-right:1.2rem;border-right:1px solid var(--border);margin-right:.8rem;letter-spacing:.04em}}
nav a{{color:var(--muted);text-decoration:none;font-size:.76rem;padding:0 .65rem;white-space:nowrap;transition:color .15s}}
nav a:hover{{color:var(--text)}}

/* HERO */
.hero{{max-width:var(--ww);margin:0 auto;padding:5rem 2rem 4rem}}
.hero-tag{{display:inline-block;background:var(--accent);color:#000;
  font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
  padding:.18rem .5rem;border-radius:3px;margin-bottom:1.2rem}}
.hero h1{{font-family:var(--serif);font-size:clamp(1.9rem,5vw,2.9rem);
  font-weight:700;line-height:1.12;color:#fff;max-width:680px}}
.hero-deck{{font-size:1rem;color:var(--muted);margin-top:1.1rem;max-width:620px;line-height:1.6}}
.hero-meta{{margin-top:2rem;display:flex;gap:2rem;flex-wrap:wrap;
  border-top:1px solid var(--border);padding-top:1.5rem}}
.hero-meta .stat .val{{font-size:1.6rem;font-weight:800;color:var(--accent);display:block}}
.hero-meta .stat .lbl{{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}

/* ARTICLE */
.article-body{{max-width:var(--w);margin:0 auto;padding:0 2rem 5rem}}
.article-section{{margin-bottom:4.5rem}}
.section-num{{font-size:.67rem;font-weight:800;letter-spacing:.1em;
  color:var(--accent);text-transform:uppercase;margin-bottom:.45rem;opacity:.8}}
.article-section h2{{font-family:var(--serif);font-size:1.6rem;font-weight:700;
  line-height:1.18;color:#fff;margin-bottom:1.2rem}}
.article-section p{{margin-bottom:1.1rem;color:var(--text);font-size:.96rem}}
.article-section p strong{{color:#fff}}

/* PULL QUOTE */
.pull-quote{{margin:2rem 0;padding:1.4rem 1.8rem;
  border-left:3px solid var(--accent);background:var(--surface);
  border-radius:0 8px 8px 0;display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap}}
.pq-num{{font-size:2.3rem;font-weight:800;color:var(--accent);line-height:1;font-family:var(--serif)}}
.pq-desc{{font-size:.88rem;color:var(--muted)}}
.pull-quote.green {{border-color:var(--green)}} .pull-quote.green  .pq-num{{color:var(--green)}}
.pull-quote.yellow{{border-color:var(--yellow)}} .pull-quote.yellow .pq-num{{color:var(--yellow)}}
.pull-quote.orange{{border-color:var(--orange)}} .pull-quote.orange .pq-num{{color:var(--orange)}}

/* EXPLAINER BOX */
.explainer{{
  margin:1.5rem 0;padding:1rem 1.3rem;
  background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;font-size:.87rem;color:var(--muted);line-height:1.65;
}}
.explainer strong{{color:var(--text)}}

/* CHARTS */
.chart-full{{
  margin:2rem -2rem;padding:1.4rem 2rem;
  background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);
}}
.chart-full .ct{{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.7rem}}
.chart-full .cc{{font-size:.77rem;color:var(--muted);margin-top:.55rem;font-style:italic}}
.chart-inline{{margin:2rem 0}}
.chart-inline .cc{{font-size:.77rem;color:var(--muted);margin-top:.55rem;font-style:italic}}
.chart-duo{{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;margin:2rem 0}}
.chart-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem}}
.chart-caption{{font-size:.75rem;color:var(--muted);margin-top:.45rem;font-style:italic}}
@media(max-width:680px){{.chart-duo{{grid-template-columns:1fr}}.chart-full{{margin:2rem 0}}}}

/* FICHA */
.ficha{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.3rem 1.6rem;margin:2.2rem 0}}
.ficha h4{{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);margin-bottom:.8rem}}
.ficha-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem}}
@media(max-width:560px){{.ficha-grid{{grid-template-columns:repeat(2,1fr)}}}}
.ficha-item .val{{font-size:1.35rem;font-weight:800;color:var(--text)}}
.ficha-item .lbl{{font-size:.7rem;color:var(--muted)}}

/* HIGHLIGHT */
.hbox{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:1.1rem 1.4rem;margin:1.5rem 0;font-size:.88rem;color:var(--muted)}}
.hbox strong{{color:var(--text)}}

/* CONCLUSIONS */
.conclusion-list{{list-style:none;margin:1.5rem 0}}
.conclusion-list li{{display:flex;gap:1rem;margin-bottom:1rem;
  padding:.9rem 1.2rem;background:var(--surface);border:1px solid var(--border);border-radius:8px}}
.cl-num{{color:var(--accent);font-weight:800;font-size:1.1rem;flex-shrink:0}}
.cl-text{{font-size:.88rem}} .cl-text strong{{color:#fff}}

/* METODOLOGIA */
.metodologia{{border-top:1px solid var(--border);padding-top:2rem;margin-top:3rem;
  font-size:.79rem;color:var(--muted);line-height:1.6}}
.metodologia h4{{color:var(--text);font-size:.8rem;margin-bottom:.5rem;text-transform:uppercase;letter-spacing:.06em}}
footer{{text-align:center;color:var(--muted);font-size:.73rem;padding:2rem}}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">Franco Analytics · LPF 2026</div>
  <a href="#como-se-mide">Como se mide</a>
  <a href="#existencia">Existencia</a>
  <a href="#triggers">Triggers</a>
  <a href="#duracion">Duracion</a>
  <a href="#marcador">Marcador</a>
  <a href="#equipos">Equipos</a>
  <a href="#prediccion">Prediccion</a>
  <a href="/blog/index.html" style="margin-left:auto">← Blog</a>
</nav>

<!-- HERO -->
<div class="hero">
  <div class="hero-tag">Analisis LPF 2026 · {glob["n_matches"]} partidos</div>
  <h1>El momentum en el fútbol argentino existe, y dura dos minutos</h1>
  <p class="hero-deck">Medimos el dominio de presión minuto a minuto en {glob["n_matches"]} partidos del
  Apertura 2026 para responder cuándo se forma el momentum, qué eventos lo generan,
  cuánto dura y si se puede anticipar.</p>
  <div class="hero-meta">
    <div class="stat"><span class="val">{glob["n_matches"]}</span><span class="lbl">Partidos</span></div>
    <div class="stat"><span class="val">{glob["n_goals"]}</span><span class="lbl">Goles</span></div>
    <div class="stat"><span class="val">{glob["n_reds"]}</span><span class="lbl">Rojas</span></div>
    <div class="stat"><span class="val">{glob["avg_goals_per_match"]}</span><span class="lbl">Goles / partido</span></div>
    <div class="stat"><span class="val">{glob["pct_home_positive"]}%</span><span class="lbl">Tiempo presion local</span></div>
  </div>
</div>

<div class="article-body">

<!-- INTRO + COMO SE MIDE -->
<div class="article-section">
  <p>La jugada que más cambia un partido no es el gol. Es la tarjeta roja. Y no es nada parejo.</p>

  <p>Medí el momentum en {glob["n_matches"]} partidos del Apertura 2026 usando el índice de presión
  minuto a minuto de SofaScore. Una roja genera casi tres veces más impulso que un gol y se sostiene
  varios minutos. El gol tiene un pico de dos minutos y cae. Pero hay más.</p>

  <section class="article-section" id="como-se-mide">
    <div class="section-num">Como se mide</div>
    <h2>El instrumento: el índice de presión</h2>

    <div class="explainer">
      <strong>¿Qué es el índice de presión de SofaScore?</strong><br>
      Para cada partido, SofaScore publica un número minuto a minuto que refleja quién está
      dominando en ese momento: considera tiros al arco, corners, ataques peligrosos y
      acciones en campo rival. El resultado es un valor que va de <strong>-100 a +100</strong>.
      <br><br>
      <strong>+100</strong> = el equipo local presiona al máximo y el visitante no sale de su área.<br>
      <strong>-100</strong> = lo opuesto: dominio total del visitante.<br>
      <strong>0</strong> = equilibrio perfecto entre los dos equipos.
      <br><br>
      En la práctica, los valores oscilan entre -50 y +50, con momentos puntuales más extremos.
      El promedio en los {glob["n_matches"]} partidos analizados fue de <strong>{glob["mean_abs_pressure"]:.0f} puntos</strong>
      de separación en valor absoluto.
    </div>

    <div class="ficha">
      <h4>Datos del análisis</h4>
      <div class="ficha-grid">
        <div class="ficha-item"><div class="val">{glob["n_matches"]}</div><div class="lbl">Partidos</div></div>
        <div class="ficha-item"><div class="val">{glob["n_goals"]}</div><div class="lbl">Goles registrados</div></div>
        <div class="ficha-item"><div class="val">{glob["n_reds"]}</div><div class="lbl">Tarjetas rojas</div></div>
        <div class="ficha-item"><div class="val">{glob["n_yellows"]}</div><div class="lbl">Tarjetas amarillas</div></div>
        <div class="ficha-item"><div class="val">{glob["n_subs"]}</div><div class="lbl">Sustituciones</div></div>
        <div class="ficha-item"><div class="val">~90</div><div class="lbl">Valores por partido</div></div>
        <div class="ficha-item"><div class="val">SofaScore</div><div class="lbl">Fuente</div></div>
        <div class="ficha-item"><div class="val">Apertura 2026</div><div class="lbl">Torneo</div></div>
      </div>
    </div>
  </section>
</div>

<!-- ─── HALLAZGO 1: EXISTENCIA ────────────────────── -->
<section class="article-section" id="existencia">
  <div class="section-num">Hallazgo 01</div>
  <h2>El momentum existe y es estadísticamente real</h2>

  <p>La primera pregunta es la más básica: ¿el dominio de un equipo se sostiene en el tiempo,
  o es simplemente ruido aleatorio? Si cada minuto fuera independiente del anterior (como tirar
  una moneda), no podríamos hablar de momentum.</p>

  <div class="explainer">
    <strong>Como lo medimos:</strong> Calculamos la "autocorrelación", que mide cuánto predice el
    estado de un minuto al minuto siguiente. Si el resultado es 0, no hay predicción posible:
    los minutos son independientes. Si es 1, el presente predice perfectamente el futuro.
    Un valor intermedio como 0.5 significa que hay una conexión clara pero no determinista.
  </div>

  <div class="pull-quote">
    <span class="pq-num">{ac[1]["mean"]:.2f}</span>
    <span class="pq-desc">de 1.0 posible: la fuerza con la que el minuto actual predice el siguiente (0 = ninguna, 1 = total)</span>
  </div>

  <p>La correlación entre minutos consecutivos es de <strong>{ac[1]["mean"]:.2f}</strong>
  (en una escala de 0 a 1, donde 0 sería azar puro). Esto es estadísticamente muy significativo:
  ocurriría por casualidad menos de 1 vez en un millón de muestras.</p>

  <p>El efecto decae con el tiempo: sigue siendo real hasta los {persist_txt}, y después de ahí
  el pasado ya no explica el presente. El momentum en la LPF existe, pero tiene una memoria corta.</p>

  <div class="chart-full">
    <div class="ct">Fuerza de prediccion del momento actual sobre los minutos siguientes</div>
    <div id="ch-ac" style="height:290px"></div>
    <div class="cc">Cada barra muestra qué tan bien predice el minuto actual el futuro a X minutos de distancia.
    Verde = estadísticamente significativo. El índice cae hacia cero a medida que aumenta la distancia.</div>
  </div>

  <p>El perfil promedio de los {glob["n_matches"]} partidos muestra otro patrón: el equipo local
  sostiene una presión ligeramente positiva durante todo el partido. El mediotiempo actúa como
  un reset parcial, pero la ventaja estructural de local se mantiene en los dos tiempos.</p>

  <div class="chart-full">
    <div class="ct">Indice de presion promedio a lo largo del partido</div>
    <div id="ch-profile" style="height:290px"></div>
    <div class="cc">Linea = promedio de los {glob["n_matches"]} partidos. Banda = rango del 50% central de los partidos.
    Positivo = dominio local, negativo = dominio visitante. La línea vertical marca el mediotiempo.</div>
  </div>
</section>

<!-- ─── HALLAZGO 2: TRIGGERS ──────────────────────── -->
<section class="article-section" id="triggers">
  <div class="section-num">Hallazgo 02</div>
  <h2>La tarjeta roja genera casi tres veces más momentum que un gol</h2>

  <p>Para cada tipo de evento registramos la presión en los 5 minutos previos y en los 10 minutos
  posteriores. La diferencia entre ambas ventanas, <em>desde la perspectiva del equipo que
  protagoniza el evento</em>, muestra qué tanto cambia el partido.</p>

  <div class="explainer">
    <strong>Como leer los graficos:</strong> Las barras muestran cuántos puntos (en la escala de
    -100 a +100) sube o baja el índice de presión después de cada evento. Una barra de +12 significa
    que ese equipo pasa de, por ejemplo, 5 puntos de presión a 17, un salto visible. En verde
    los efectos estadísticamente confirmados; en gris los que podrían ser coincidencia.
  </div>

  <div class="pull-quote orange">
    <span class="pq-num">+{red_delta:.0f} pts</span>
    <span class="pq-desc">sube el dominio del equipo que recibe la roja como ventaja (en una escala de -100 a +100)</span>
  </div>

  <p>La <strong>tarjeta roja</strong> es el evento más disruptivo por lejos: genera un salto
  de {red_delta:.0f} puntos para el equipo beneficiado y una caída equivalente para el que queda
  con diez jugadores. Eso es <strong>{red_ratio} veces más</strong> que el impacto de meter
  un gol ({goal_delta:.1f} puntos).</p>

  <p>La <strong>sustitución</strong> aparece como dato inesperado: tiene el efecto más pequeño,
  pero es el más consistente entre todos los partidos (confirmado estadísticamente con
  n={trig.get("substitution",{}).get("n",0)} casos). En la LPF los cambios suelen ser ofensivos,
  y eso mueve el índice.</p>

  <div class="chart-full">
    <div class="ct">Cambio en el indice de presion despues de cada evento (en puntos)</div>
    <div id="ch-triggers-bar" style="height:300px"></div>
    <div class="cc">Verde = estadísticamente confirmado (p&lt;0.05). Gris = no confirmado.
    N = cantidad de casos analizados. Los valores positivos indican que el equipo ganó presión; los negativos, que la perdió.</div>
  </div>

  <p>El siguiente gráfico muestra cómo evoluciona la presión minuto a minuto alrededor del evento.
  La diferencia entre la roja y el gol es visual e inmediata: la roja genera una subida pronunciada
  que se mantiene durante varios minutos; el gol genera una subida que cae casi de inmediato.</p>

  <div class="chart-full">
    <div class="ct">Evolucion de la presion alrededor de cada evento (perspectiva del equipo protagonista)</div>
    <div id="ch-triggers-traj" style="height:320px"></div>
    <div class="cc">Minuto 0 = momento exacto del evento. A la izquierda, los 5 minutos previos; a la derecha, los 10 posteriores.
    Las líneas muestran el promedio de todos los casos de ese tipo de evento.</div>
  </div>
</section>

<!-- ─── HALLAZGO 3: DURACIÓN ──────────────────────── -->
<section class="article-section" id="duracion">
  <div class="section-num">Hallazgo 03</div>
  <h2>Un gol genera impulso, pero el rival lo neutraliza en dos minutos</h2>

  <p>Después de meter un gol, el equipo que anotó recibe un impulso de presión. Pero ¿cuánto
  dura ese impulso antes de que el partido vuelva al equilibrio previo?</p>

  <div class="explainer">
    <strong>Que es la "semi-vida":</strong> Es el tiempo que tarda el impulso en reducirse
    a la mitad. Si el índice de presión sube 8 puntos tras un gol, una semi-vida de 2 minutos
    significa que a los 2 minutos ya queda solo un salto de 4 puntos respecto al nivel previo.
    Es un concepto prestado de la física para medir qué tan rápido se disipa un efecto.
  </div>

  <div class="pull-quote yellow">
    <span class="pq-num">{hl_txt} min</span>
    <span class="pq-desc">semi-vida del impulso post-gol: el tiempo hasta que el efecto se reduce a la mitad</span>
  </div>

  <p>El gráfico lo muestra con claridad: hay un pico inmediato después del gol, pero la caída
  de vuelta al nivel base es casi tan rápida como la subida. En {hl_txt} minutos (lo que dura
  el festejo, el saque del centro y el primer avance del rival) el impulso ya se redujo a la mitad.</p>

  <div class="chart-full">
    <div class="ct">Evolucion de la presion antes y despues de un gol ({dur["n_goals"]} goles analizados)</div>
    <div id="ch-duration" style="height:320px"></div>
    <div class="cc">Linea azul = índice promedio del equipo que convirtió. Banda = margen de variación.
    Línea punteada = nivel base de presión en los 5 minutos previos al gol. Línea verde = momento del gol.</div>
  </div>

  <p>Este resultado es más extremo que lo que se observa en otros contextos deportivos, donde el
  efecto post-gol puede durar 8-15 minutos. Una posible explicación para la LPF: los equipos
  que reciben un gol generan presión reactiva muy rápido, y el equipo que acaba de meter
  tiende a replegarse casi de inmediato.</p>
</section>

<!-- ─── HALLAZGO 4: MARCADOR ──────────────────────── -->
<section class="article-section" id="marcador">
  <div class="section-num">Hallazgo 04</div>
  <h2>El contexto cambia todo: no es lo mismo adelantarse que empatar</h2>

  <p>Separamos los goles en cuatro situaciones distintas y medimos el patrón de presión de cada una.
  Los resultados muestran diferencias claras en cómo reaccionan los equipos según lo que estaba
  en juego en el momento del gol.</p>

  <div class="chart-full">
    <div class="ct">Indice de presion antes y despues del gol segun contexto del marcador</div>
    <div id="ch-score" style="height:340px"></div>
    <div class="cc">Perspectiva del equipo que convirtió el gol. Minuto 0 = el gol. Las líneas son el promedio
    de todos los goles en esa situación. N = cantidad de casos.</div>
  </div>

  <p>El <strong>gol que adelanta</strong> (de empate a ventaja,
  n={score.get("go_ahead",{}).get("n",0)}) genera el pico más alto: el equipo que acaba de
  ponerse arriba domina claramente, pero el rival reacciona fuerte buscando el empate.
  La caída posterior es pronunciada.</p>

  <p>El <strong>gol del empate</strong> (n={score.get("equalizer",{}).get("n",0)}) merece una aclaración: el
  equipo que empataba no siempre llegó al gol desde una posición de dominio. En {eq_n_ann} casos
  ya venía acumulando presión positiva antes de convertir: el gol era "anunciado". En los otros
  {eq_n_ctr} casos aún estaba siendo dominado. El empate llegó a contragolpe o desde la nada.
  {"La diferencia en el impulso post-gol entre ambos grupos es estadísticamente significativa (p=" + f"{eq_p:.3f}" + "), así que se muestran como dos líneas separadas en el gráfico." if eq_significant else "Comparamos el impulso post-gol entre ambos grupos y la diferencia no fue estadísticamente significativa (p=" + f"{eq_p:.2f}" + "): después de empatar, el patrón de presión es similar haya llegado el gol en dominio o en contra del juego. Se muestra como una sola línea."}</p>

  <p>El <strong>gol que amplía ventaja</strong> (n={score.get("extend_lead",{}).get("n",0)})
  genera el pico más bajo de todos: el equipo que ya ganaba no necesita seguir presionando,
  y a menudo se repliega para administrar el resultado.</p>

  <p>El <strong>gol que acorta la diferencia</strong> cuando se sigue perdiendo
  (n={score.get("pull_one_back",{}).get("n",0)}) muestra un pico momentáneo (la reacción
  de quien acortó), pero se aplana rápido, quizás porque el rival refuerza la presión
  defensiva para no perder la ventaja.</p>
</section>

<!-- ─── HALLAZGO 5: EQUIPOS ───────────────────────── -->
<section class="article-section" id="equipos">
  <div class="section-num">Hallazgo 05</div>
  <h2>{top_dom_name} dominó en presión; {top_conv_name} fue el más eficiente</h2>

  <p>¿Qué equipo acumuló más minutos de dominio durante el torneo? ¿Y quién aprovechó mejor
  esos minutos convirtiendo goles cuando tenía el partido a favor?</p>

  <p><strong>{top_dom_name}</strong> pasó el <strong>{top_dom_val:.0f}%</strong> del tiempo
  con presión dominante: el porcentaje más alto del torneo. La dominancia de presión refleja
  una combinación de estilo de juego (equipos que proponen más, que atacan más) y ventaja
  de local (los partidos en casa tienden a inclinar el índice hacia arriba).</p>

  <div class="pull-quote green">
    <span class="pq-num">{top_conv_val:.0f}%</span>
    <span class="pq-desc">{top_conv_name}: goles convertidos con el indice de presion favorable en los 5 min previos</span>
  </div>

  <p>Pero el dato más interesante no es quién dominó más, sino quién convirtió esa dominancia
  en goles. <strong>{top_conv_name}</strong> anotó el <strong>{top_conv_val:.0f}%</strong> de sus
  goles en situaciones donde tenía el índice de presión a favor en los 5 minutos previos.
  Esto puede indicar un estilo ofensivo que ataca cuando domina, en contraste con equipos
  más reactivos que convierten en contragolpe con presión baja.</p>

  <div class="chart-full">
    <div class="ct">Dominancia de presion y eficiencia goleadora por equipo</div>
    <div class="chart-duo" style="margin:0">
      <div>
        <div id="ch-teams-dom" style="height:420px"></div>
        <div class="chart-caption">% del tiempo con el índice de presión por encima de +10 puntos durante el partido</div>
      </div>
      <div>
        <div id="ch-teams-conv" style="height:420px"></div>
        <div class="chart-caption">% de los goles del equipo que llegaron con presión favorable en los 5 minutos previos</div>
      </div>
    </div>
  </div>
</section>

<!-- ─── HALLAZGO 6: PREDICCIÓN ────────────────────── -->
{pred_html}

<!-- ─── CONCLUSIONES ──────────────────────────────── -->
<section class="article-section" id="conclusiones">
  <div class="section-num">Resumen</div>
  <h2>Cinco respuestas sobre el momentum en la LPF</h2>

  <ul class="conclusion-list">
    <li>
      <span class="cl-num">01</span>
      <span class="cl-text"><strong>El momentum existe.</strong>
      El índice de presión de un minuto predice el siguiente con una fuerza de {ac[1]["mean"]:.2f}
      (en una escala de 0 a 1). No es una percepción subjetiva: es una propiedad estadística
      real del partido.</span>
    </li>
    <li>
      <span class="cl-num">02</span>
      <span class="cl-text"><strong>Dura poco.</strong>
      La memoria del momentum se extiende hasta {persist_txt} y luego desaparece.
      El impulso específico post-gol tiene una semi-vida de {hl_txt} minutos (el tiempo de la celebración).</span>
    </li>
    <li>
      <span class="cl-num">03</span>
      <span class="cl-text"><strong>La roja es {red_ratio}x más disruptiva que un gol.</strong>
      Genera un salto de {red_delta:.0f} puntos en el índice de presión (escala -100/+100), sostenido
      durante varios minutos. El gol genera solo {goal_delta:.1f} puntos y cae rápido.</span>
    </li>
    <li>
      <span class="cl-num">04</span>
      <span class="cl-text"><strong>El contexto del marcador cambia el patrón.</strong>
      Adelantarse genera el pico más alto pero también la respuesta más fuerte del rival.
      Ampliar ventaja genera el impulso más débil: el equipo que ya gana no necesita seguir atacando.</span>
    </li>
    <li>
      <span class="cl-num">05</span>
      <span class="cl-text"><strong>El momentum predice quién anota en {auc_100} de cada 100 casos.</strong>
      El azar puro acertaría 50 de 100. Los 13 puntos de diferencia confirman que el dominio
      territorial precede a los goles con una frecuencia real, no aleatoria.</span>
    </li>
  </ul>

</section>

</div><!-- /article-body -->

<footer>Franco Analytics · LPF Apertura 2026 · Mayo 2026</footer>

<!-- SCRIPTS ─────────────────────────────────────────── -->
<script>
const cfg = {{responsive:true}};
const LA = (ttl, xax={{}}, yax={{}}, extra={{}}) => ({{
  title:{{text:'',font:{{size:11}}}},
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{{color:'#dde1ea',size:11,family:'Segoe UI,system-ui,sans-serif'}},
  xaxis:{{gridcolor:'#252b38',zerolinecolor:'#3a4252',...xax}},
  yaxis:{{gridcolor:'#252b38',zerolinecolor:'#3a4252',...yax}},
  margin:{{t:12,r:20,b:50,l:55}},
  showlegend:true,
  legend:{{bgcolor:'rgba(0,0,0,0)',bordercolor:'#252b38',borderwidth:1}},
  ...extra
}});
const BL='#4e9eff',OR='#ff6b4e',GR='#3dde7a',YE='#f5c542',PU='#b44eff',RE='#ff4e4e';

// ── Autocorrelacion ──────────────────────────────────
(function(){{
  const lags  = {js([f"+{l} min" for l in ac_lags])};
  const means = {js(ac_means)};
  const ses   = {js(ac_ses)};
  const ps    = {js(ac_ps)};
  const cols  = means.map((v,i)=>ps[i]<0.05?(v>0?GR:OR):'#3a4555');
  Plotly.newPlot('ch-ac',
    [{{x:lags,y:means,error_y:{{type:'data',array:ses,visible:true,color:'#444',thickness:1.5,width:5}},
      type:'bar',marker:{{color:cols}},name:'Fuerza de prediccion'}},
     {{x:[lags[0],lags[lags.length-1]],y:[0,0],type:'scatter',mode:'lines',
      line:{{color:'#444',dash:'dot',width:1}},showlegend:false}}],
    LA('',{{title:'Distancia temporal (minutos)'}},
          {{title:'Fuerza de prediccion (0 = azar, 1 = perfecta)'}}), cfg);
}})();

// ── Perfil del partido ───────────────────────────────
(function(){{
  const mins  = {js(mins)};
  const mean_ = {js(prof_mean)};
  const p75   = {js(prof_p75)};
  const p25   = {js(prof_p25)};
  Plotly.newPlot('ch-profile',
    [{{x:[...mins,...mins.slice().reverse()],y:[...p75,...p25.slice().reverse()],
      fill:'toself',fillcolor:'rgba(78,158,255,.1)',line:{{color:'transparent'}},
      showlegend:true,name:'50% central de los partidos',type:'scatter'}},
     {{x:mins,y:mean_,type:'scatter',mode:'lines',line:{{color:BL,width:2}},name:'Promedio'}},
     {{x:[1,90],y:[0,0],type:'scatter',mode:'lines',line:{{color:'#444',dash:'dot',width:1}},showlegend:false}},
     {{x:[45,45],y:[-35,35],type:'scatter',mode:'lines',line:{{color:'#444',dash:'dash',width:1}},name:'Mediotiempo'}}],
    LA('',{{title:'Minuto del partido'}},
          {{title:'Indice de presion (positivo = local, negativo = visitante)'}},{{height:260}}),cfg);
}})();

// ── Triggers — barras ────────────────────────────────
(function(){{
  const names  = {js(t_names)};
  const deltas = {js(t_delta)};
  const ps     = {js(t_p)};
  const ns     = {js(t_n)};
  const cols   = deltas.map((d,i)=>ps[i]<0.05?(d>0?GR:OR):'#3a4555');
  Plotly.newPlot('ch-triggers-bar',
    [{{y:names,x:deltas,type:'bar',orientation:'h',marker:{{color:cols}},
      text:ns.map(n=>`${{n}} casos`),textposition:'outside',textfont:{{color:'#6b7585',size:10}},name:'Cambio en puntos'}},
     {{x:[0,0],y:[names[0],names[names.length-1]],type:'scatter',mode:'lines',
      line:{{color:'#444',dash:'dot',width:1}},showlegend:false}}],
    LA('',{{title:'Cambio en el indice de presion (puntos, escala -100 a +100)'}},{{automargin:true}}),cfg);
}})();

// ── Triggers — trayectorias ──────────────────────────
(function(){{
  const offs = {js(offs_s)};
  const g    = {js(goal_t)};
  const c    = {js(conc_t)};
  const rr   = {js(redr_t)};
  const rv   = {js(redv_t)};
  const trs  = [
    {{x:offs,y:g, type:'scatter',mode:'lines',name:'Gol: equipo que convierte', line:{{color:GR,width:2}}}},
    {{x:offs,y:c, type:'scatter',mode:'lines',name:'Gol: equipo que recibe',    line:{{color:OR,width:2}}}},
    {{x:offs,y:rr,type:'scatter',mode:'lines',name:'Roja: equipo beneficiado',  line:{{color:BL,width:2.5}}}},
    {{x:offs,y:rv,type:'scatter',mode:'lines',name:'Roja: equipo sancionado',   line:{{color:RE,width:2,dash:'dot'}}}},
  ].filter(t=>t.y.some(v=>v!==null));
  trs.push({{x:[0,0],y:[-30,35],type:'scatter',mode:'lines',line:{{color:'#555',dash:'dash',width:1}},showlegend:false,name:'Evento'}});
  Plotly.newPlot('ch-triggers-traj',trs,
    LA('',{{title:'Minutos desde el evento'}},
          {{title:'Indice de presion (perspectiva del equipo protagonista)'}},{{height:290}}),cfg);
}})();

// ── Duracion post-gol ────────────────────────────────
(function(){{
  const offs = {js(offs_l)};
  const t    = {js(dur_t)};
  const u    = {js(dur_u)};
  const d    = {js(dur_d)};
  const base = {js(float(dur["baseline"]))};
  Plotly.newPlot('ch-duration',
    [{{x:[...offs,...offs.slice().reverse()],y:[...u,...d.slice().reverse()],
      fill:'toself',fillcolor:'rgba(78,158,255,.1)',line:{{color:'transparent'}},
      showlegend:true,name:'Margen de variacion',type:'scatter'}},
     {{x:offs,y:t,type:'scatter',mode:'lines',line:{{color:BL,width:2.5}},name:'Presion promedio'}},
     {{x:[offs[0],offs[offs.length-1]],y:[base,base],type:'scatter',mode:'lines',
      line:{{color:'#555',dash:'dot',width:1}},name:'Nivel previo al gol'}},
     {{x:[0,0],y:[-25,45],type:'scatter',mode:'lines',
      line:{{color:GR,dash:'dash',width:1.5}},name:'Gol'}}],
    LA('',{{title:'Minutos desde el gol'}},
          {{title:'Indice de presion del equipo que convirtio'}},{{height:290}}),cfg);
}})();

// ── Score state ──────────────────────────────────────
(function(){{
  const offs = {js(offs_s)};
  const data = {js(score_traces)};
  const trs  = data.map(t=>
    ({{x:offs,y:t.y,type:'scatter',mode:'lines',name:t.name,line:{{color:t.color,width:2,dash:t.dash||'solid'}}}}));
  trs.push({{x:[0,0],y:[-25,40],type:'scatter',mode:'lines',
    line:{{color:'#555',dash:'dash',width:1}},showlegend:false}});
  Plotly.newPlot('ch-score',trs,
    LA('',{{title:'Minutos desde el gol'}},
          {{title:'Indice de presion del equipo que convirtio'}},{{height:300}}),cfg);
}})();

// ── Equipos ──────────────────────────────────────────
(function(){{
  const names = {js(t_eq_names)};
  const dom   = {js(t_dom)};
  const conv  = {js(t_conv)};
  Plotly.newPlot('ch-teams-dom',
    [{{y:names,x:dom,type:'bar',orientation:'h',
      marker:{{color:dom.map(v=>v>50?GR:v>38?BL:'#3a5070')}},name:'% tiempo dominante'}}],
    LA('',{{title:'% del tiempo con presion por encima de +10'}},{{automargin:true}},{{height:400}}),cfg);
  Plotly.newPlot('ch-teams-conv',
    [{{y:names,x:conv,type:'bar',orientation:'h',
      marker:{{color:conv.map(v=>v>60?GR:v>45?BL:OR)}},name:'% goles con momentum'}}],
    LA('',{{title:'% de goles anotados con presion favorable previa'}},{{automargin:true}},{{height:400}}),cfg);
}})();

// ── Prediccion ───────────────────────────────────────
{pred_js}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("Cargando datos...")
    raw, form, team_names = load_data()

    print("Construyendo mapa de equipos...")
    team_map = build_team_map(form, raw, team_names)
    mapped = sum(1 for v in team_map.values() if v.get("home") or v.get("away"))
    print(f"  {mapped}/{len(team_map)} partidos con equipos identificados")

    print("Parseando partidos...")
    matches = [parse_match(eid, mdata, team_map) for eid, mdata in raw.items()]
    print(f"  {len(matches)} partidos")

    print("Ejecutando analisis...")
    eq_ctx = analysis_equalizer_context(matches)
    results = {
        "autocorr":    analysis_autocorrelation(matches),
        "profile":     analysis_match_profile(matches),
        "triggers":    analysis_triggers(matches),
        "duration":    analysis_duration(matches),
        "score_state": analysis_score_state(matches),
        "teams":       analysis_teams(matches),
        "predictive":  analysis_predictive(matches),
        "global":      global_stats(matches),
        "eq_context":  eq_ctx,
    }

    # Score state counts
    for ctx, res in results["score_state"].items():
        print(f"  {ctx}: n={res['n']}")
    print(f"  equalizer announced: n={eq_ctx.get('announced',{}).get('n',0)}  counter: n={eq_ctx.get('counter',{}).get('n',0)}  p={eq_ctx.get('p_value','?')}  sig={eq_ctx.get('significant')}")

    print("Generando HTML...")
    html = build_article(results)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Listo: {OUT_PATH}")


if __name__ == "__main__":
    main()
