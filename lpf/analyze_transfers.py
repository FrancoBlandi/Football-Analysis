#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimización de transferencias FM — formación libre.
Prueba todas las formaciones válidas × C(10,5)=252 combinaciones de quién conservar.
Molinas siempre se vende (sin fixture).
"""
import json, re, sys, io, unicodedata
from pathlib import Path
from itertools import combinations

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ANALYTICS_HTML   = Path("c:/Users/Franco/Franco Analytics/lpf/analytics.html")
BUDGET_REMAINING = 3.98

# Formaciones válidas: (DEF, MID, FWD) — GK siempre 1
# Restricciones: max 5 DEF, max 5 MID, max 4 FWD, min 3 DEF, min 3 MID, min 1 FWD
VALID_FORMATIONS = [
    (3, 3, 4),
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 3, 2),
    (5, 4, 1),
]

def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

# ── Parsear analytics.html ──
with open(ANALYTICS_HTML, encoding="utf-8") as f:
    html = f.read()

start = html.find("const D = {")
depth, end = 0, 0
for j in range(start + len("const D = "), len(html)):
    if html[j] == "{": depth += 1
    elif html[j] == "}":
        depth -= 1
        if depth == 0:
            end = j + 1
            break

players = json.loads(html[start + len("const D = "):end])["players"]
by_name = {norm(p["name"]): p for p in players}

def find_player(name):
    n = norm(name)
    if n in by_name: return by_name[n]
    parts = n.split()
    cands = [p for k, p in by_name.items() if parts[-1] in k.split()]
    if len(cands) == 1: return cands[0]
    for c in cands:
        if len(parts) >= 2 and parts[0] in norm(c["name"]).split():
            return c
    return None

def get_pos(p):
    pos = (p.get("pos") or "").upper()
    if pos in ("G","GK"): return "GK"
    if pos in ("D","DEF","CB","LB","RB","WB"): return "DEF"
    if pos in ("M","MID","CM","DM","AM"):       return "MID"
    if pos in ("F","FWD","ST","LW","RW","ATT","A"): return "FWD"
    return "UNK"

# ── Equipo actual ──
starters = [
    ("Facundo Cambeses",  "GK",  7.80),
    ("Mateo Del Blanco",  "DEF", 5.00),
    ("Gonzalo Montiel",   "DEF", 7.50),
    ("Lautaro Blanco",    "DEF", 7.40),
    ("Lucas Zelarayan",   "MID", 7.50),
    ("Franco Vazquez",    "MID", 4.68),
    ("Aaron Molinas",     "MID", 5.80),  # sin fixture — siempre se vende
    ("Leandro Paredes",   "MID", 9.05),
    ("Miguel Merentiel",  "FWD",10.90),
    ("Nicolas Fernandez", "FWD", 7.20),
    ("Gabriel Avalos",    "FWD", 7.52),
]
MOLINAS_IDX = 6

current = {}
for name, pos, price in starters:
    p = find_player(name)
    current[name] = {
        "xpts":  (p.get("xpts") or 0.0) if p else 0.0,
        "price": price, "pos": pos,
    }

total_now = sum(v["xpts"] for v in current.values())

# ── Pools de candidatos por posición (excluye titulares actuales) ──
starter_norms = {norm(s[0]) for s in starters}
pool = {"GK": [], "DEF": [], "MID": [], "FWD": []}
for p in players:
    pg = get_pos(p)
    if pg == "UNK" or norm(p["name"]) in starter_norms: continue
    if (p.get("xpts") or 0) > 0 and (p.get("fm_price") or 0) > 0:
        pool[pg].append(p)
for pg in pool:
    pool[pg].sort(key=lambda x: x.get("xpts") or 0, reverse=True)

def best_buy(positions_needed, budget):
    """
    Dado un dict {pos: count} y un presupuesto, retorna la lista de jugadores
    que maximiza xPts total. Greedy global: ordena todos los candidatos por xPts
    desc y asigna mientras quede budget y plazas.
    """
    # Candidatos únicos expandidos
    all_cands = []
    seen = set()
    for pg, cnt in positions_needed.items():
        for p in pool[pg][:60]:
            n = norm(p["name"])
            if n not in seen:
                seen.add(n)
                all_cands.append((pg, p))
    all_cands.sort(key=lambda x: x[1].get("xpts") or 0, reverse=True)

    chosen    = []
    used      = set()
    rem       = budget
    filled    = {pg: 0 for pg in positions_needed}

    for pg, p in all_cands:
        if filled.get(pg, 0) >= positions_needed.get(pg, 0): continue
        n     = norm(p["name"])
        price = p.get("fm_price") or 0
        if n in used or price > rem: continue
        chosen.append((pg, p))
        used.add(n)
        filled[pg] = filled.get(pg, 0) + 1
        rem -= price
        if sum(filled.values()) == sum(positions_needed.values()): break

    return chosen, rem


# ── Optimización: formaciones × combinaciones ──
non_molinas = [i for i in range(len(starters)) if i != MOLINAS_IDX]
best_result = None
best_xpts   = -999

for formation in VALID_FORMATIONS:
    d_t, m_t, f_t = formation

    for keep_idx in combinations(non_molinas, 5):
        keep_set = set(keep_idx)

        # Posiciones de los conservados
        gk_k  = sum(1 for i in keep_set if starters[i][1] == "GK")
        def_k = sum(1 for i in keep_set if starters[i][1] == "DEF")
        mid_k = sum(1 for i in keep_set if starters[i][1] == "MID")
        fwd_k = sum(1 for i in keep_set if starters[i][1] == "FWD")

        # Los conservados deben caber en la formación objetivo
        if gk_k > 1 or def_k > d_t or mid_k > m_t or fwd_k > f_t:
            continue

        # Slots que hay que comprar
        need = {}
        if 1 - gk_k  > 0: need["GK"]  = 1 - gk_k
        if d_t - def_k > 0: need["DEF"] = d_t - def_k
        if m_t - mid_k > 0: need["MID"] = m_t - mid_k
        if f_t - fwd_k > 0: need["FWD"] = f_t - fwd_k

        if sum(need.values()) != 6:
            continue  # debe haber exactamente 6 compras

        sell_idx  = [i for i in range(len(starters)) if i not in keep_set]
        sell_price = sum(starters[i][2] for i in sell_idx)
        budget     = sell_price + BUDGET_REMAINING

        chosen, budget_left = best_buy(need, budget)
        if sum(1 for _ in chosen) < 6:
            continue

        xpts_kept = sum(current[starters[i][0]]["xpts"] for i in keep_set)
        xpts_new  = sum(p.get("xpts", 0) for _, p in chosen)
        total     = xpts_kept + xpts_new

        if total > best_xpts:
            best_xpts   = total
            best_result = {
                "formation":   formation,
                "keep_idx":    keep_set,
                "sell_idx":    sell_idx,
                "need":        need,
                "budget":      budget,
                "budget_left": budget_left,
                "chosen":      chosen,
                "xpts_kept":   xpts_kept,
                "xpts_new":    xpts_new,
                "total":       total,
            }

# ── Output ──
fmt = best_result["formation"]
print(f"Formaciones evaluadas: {len(VALID_FORMATIONS)}  |  Combinaciones: {len(VALID_FORMATIONS)*252}")
print(f"\nxPts actuales: {total_now:.2f}")
print(f"xPts óptimos:  {best_xpts:.2f}  (+{best_xpts-total_now:.2f})")
print(f"Formación óptima: {fmt[0]}-{fmt[1]}-{fmt[2]}\n")

sell_names = {starters[i][0] for i in best_result["sell_idx"]}
print("=== EQUIPO ACTUAL ===")
for name, pos, price in starters:
    tag  = " [VENDER]" if name in sell_names else ""
    flag = " *** SIN FIXTURE" if "Molinas" in name else ""
    arrow = "→" if name in sell_names else " "
    print(f"  {arrow} {name:<24} {pos:>4}  ${price:>5.2f}M  {current[name]['xpts']:>5.2f} xPts{tag}{flag}")

print(f"\n=== 6 TRANSFERENCIAS ===")
print(f"  Presupuesto de ventas: ${sum(starters[i][2] for i in best_result['sell_idx']):.2f}M  +  saldo ${BUDGET_REMAINING:.2f}M  =  total ${best_result['budget']:.2f}M")
print(f"  Budget sobrante: ${best_result['budget_left']:.2f}M\n")

# Emparejar vendidos → comprados en orden global (no por posición)
# Necesario cuando la formación cambia y hay cross-position swaps
sells_flat = [starters[i] for i in best_result["sell_idx"]]
buys_flat  = [p for _, p in best_result["chosen"]]

# Ordenar ambas listas por posición para display consistente
pos_order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
sells_flat.sort(key=lambda x: pos_order.get(x[1], 9))
buys_flat.sort(key=lambda x: pos_order.get((x.get("pos") or "").upper(), 9))

print(f"  {'OUT':<24} {'Pos':>3}  {'xPts':>5}  →  {'IN':<24} {'Pos':>3}  {'xPts':>5}  {'VOR':>6}  {'Precio':>7}  {'xPts/M$':>8}  Rival")
print("  " + "-" * 112)

total_vor = 0
for (name_out, pos_out, price_out), p_in in zip(sells_flat, buys_flat):
    out_x  = current[name_out]["xpts"]
    in_x   = p_in.get("xpts", 0)
    pos_in = (p_in.get("pos") or "").upper()
    vor    = in_x - out_x
    total_vor += vor
    xpm    = p_in.get("xpts_per_m")
    xpm_s  = f"{xpm:.2f}" if xpm else "—"
    cost   = p_in.get("fm_price", 0)
    arrow  = "  " if pos_out == pos_in else "⇄"
    print(f"  {name_out:<24} {pos_out:>3}  {out_x:>5.2f}  {arrow}→  {p_in['name']:<24} {pos_in:>3}  {in_x:>5.2f}  {vor:>+6.2f}  ${cost:>5.2f}M  {xpm_s:>8}  FDR{p_in.get('fdr_opp','?')} ({p_in.get('club','')})")

print(f"\n  VOR total: +{total_vor:.2f}  |  xPts: {total_now:.2f} → {best_xpts:.2f}")

print(f"\n=== EQUIPO FINAL ({fmt[0]}-{fmt[1]}-{fmt[2]}) ===")
final = []
for i in best_result["keep_idx"]:
    name, pos, price = starters[i]
    final.append((pos, name, price, current[name]["xpts"], False))
for pg, p in best_result["chosen"]:
    final.append((pg, p["name"], p.get("fm_price",0), p.get("xpts",0), True))

order = {"GK":0,"DEF":1,"MID":2,"FWD":3}
final.sort(key=lambda x: order.get(x[0],9))

print(f"  {'Jugador':<26} {'Pos':>4}  {'Precio':>7}  {'xPts':>6}  {'xPts/M$':>8}")
print("  " + "-"*65)
for pos, name, price, xpts, is_new in final:
    xpm = round(xpts/price, 2) if price > 0 else None
    tag = " ◄" if is_new else ""
    print(f"  {name:<26} {pos:>4}  ${price:>5.2f}M  {xpts:>6.2f}  {xpm if xpm else '—':>8}{tag}")

print(f"\n  TOTAL xPts: {best_xpts:.2f}")

