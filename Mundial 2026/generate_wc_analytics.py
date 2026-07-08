#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_wc_analytics.py — Modelo xPts Fantasy Manager para el Mundial 2026
Metodología análoga a generate_analytics.py (LPF) con adaptaciones:

Diferencias clave vs LPF:
  - Stats base = blend(club 2024-25, intl reciente) en vez de torneo único
  - Forma = últimos 5 partidos con la selección (weight 0.25 vs 0.55 en LPF)
  - Sin BPR / sin precios (no disponibles para el Mundial)
  - FDR calculado desde resultados recientes de cada selección
  - 12 grupos (A-L), 3 fechas de grupo cada una

Uso:
    python "Mundial 2026/generate_wc_analytics.py"
    python "Mundial 2026/generate_wc_analytics.py" --fecha 1   # solo fecha 1 de grupos
"""

import json, math, sys, io, argparse
from pathlib import Path
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR          = Path(__file__).parent
PLAYER_PATH       = BASE_DIR / "wc2026_player_stats.json"
FORM_PATH         = BASE_DIR / "wc2026_form.json"
TEAM_PATH         = BASE_DIR / "wc2026_team_stats.json"
FIXTURES_PATH     = BASE_DIR / "wc2026_fixtures.json"
LINEUPS_PATH      = BASE_DIR / "wc2026_lineups.json"
SETPIECES_PATH    = BASE_DIR / "wc2026_setpieces.json"
PREDICTIONS_PATH  = BASE_DIR / "wc2026_predictions.json"
COACHES_PATH      = BASE_DIR / "wc2026_coaches.json"
MATCH_ANALYTICS_PATH = BASE_DIR / "wc2026_match_analytics.json"
WC_RESULTS_PATH   = BASE_DIR / "wc2026_wc_results.json"
OUT_PATH          = BASE_DIR / "analytics_wc.html"

HOST_NATIONS = {"USA", "Canada", "Mexico"}

# Jugadores que se espera que sean suplentes (reducen p_over60 significativamente)
BAJA_OVERRIDES = {
    # Confirmados fuera del squad (SofaScore oficial)
    885908,   # Reece James (England) — lesión, se pierde todo el torneo
    928236,   # Leonardo Balerdi (Argentina)
    124712,   # Neymar (Brazil) — no convocado al Mundial 2026
    1134351,  # Ismael Koné (Canada) — lesión confirmada F2, no juega F3
    1134200,  # Wesley (Brazil)
    1861975,  # Lennart Karl (Germany)
    958959,   # Jurriën Timber (Netherlands)
    143040,   # Wataru Endo (Japan)
    877102,   # Nayef Aguerd (Morocco)
    1011375,  # Abdessamad Ezzalzouli (Morocco)
    973556,   # Julio Enciso (Paraguay)
    1084295,  # Marcelo Flores (Canada)
    825956,   # Christoph Baumgartner (Austria)
    855970,   # Deni Jurić (Australia)
    214308,   # Martin Boyle (Australia)
    835998,   # Riley McGree (Australia)
    822572,   # Kye Rowles (Australia)
    1021272,  # Daniel Svensson (Sweden)
    1026122,  # Yu-min Cho (South Korea)
    # Suspensiones por roja en Octavos (round_num=4)
    934237,   # Folarin Balogun (USA) — roja min 64 vs Bosnia → suspendido vs Bélgica
}

SUPLENTE_OVERRIDES = {
    # (vacío — la detección automática por minutos internacionales es suficiente)
}

ROTACIONAL_OVERRIDES = {
    # El threshold de 180 min WC (2+ partidos) cubre la mayoría de los casos automáticamente.
    # Solo agregar aquí jugadores con situación especial que el threshold no detecta.
}

# Solo jugadores donde la auto-detección por minutos falla
# (avg intl < 60min pero son titulares reales según XI proyectados)
# Jugadores con avg >= 60min NO necesitan estar aquí — la auto-detección los toma como Titular
STARTER_OVERRIDES = {
    # Auto-detectado desde lineups reales de fecha 1
}

# ── Calidad de liga (análogo a coeficiente Bota de Oro) ───────────────────────
# Multiplicador aplicado a xg90/xa90 del club antes de la regresión bayesiana.
# Top 5 europeas = 1.0 ; ligas débiles = 0.55
_CLUB_Q = {
    # Premier League
    "Liverpool": 1.00, "Manchester City": 1.00, "Arsenal": 1.00, "Chelsea": 1.00,
    "Manchester United": 1.00, "Tottenham": 1.00, "Newcastle": 1.00,
    "Aston Villa": 1.00, "Brighton": 0.97, "West Ham": 0.97,
    "Wolverhampton": 0.96, "Crystal Palace": 0.96, "Brentford": 0.96,
    "Nottingham": 0.96, "Everton": 0.95, "Leicester": 0.95,
    # Bundesliga
    "Bayern": 1.00, "Bayer Leverkusen": 1.00, "Borussia Dortmund": 0.98,
    "RB Leipzig": 0.97, "Eintracht Frankfurt": 0.96, "Freiburg": 0.94,
    "Hoffenheim": 0.93, "Augsburg": 0.92, "Stuttgart": 0.95,
    # LaLiga
    "Real Madrid": 1.00, "Barcelona": 1.00, "Atlético": 0.98,
    "Athletic": 0.96, "Villarreal": 0.95, "Real Sociedad": 0.95,
    "Sevilla": 0.94, "Real Betis": 0.93, "Girona": 0.93, "Osasuna": 0.91,
    "Real Oviedo": 0.80,
    # Serie A
    "Juventus": 0.97, "Inter": 0.97, "AC Milan": 0.97, "Napoli": 0.97,
    "Atalanta": 0.96, "Roma": 0.95, "Lazio": 0.95, "Fiorentina": 0.94,
    "SSC Napoli": 0.97, "Inter Milan": 0.97,
    # Ligue 1
    "PSG": 0.97, "Paris Saint": 0.97, "Monaco": 0.94,
    "Marseille": 0.93, "Lyon": 0.93, "Lille": 0.93, "Lens": 0.91,
    # Primeira Liga
    "Sporting CP": 0.88, "Porto": 0.88, "Benfica": 0.88,
    "Braga": 0.85, "Sporting Braga": 0.85,
    # Eredivisie
    "Ajax": 0.87, "PSV": 0.87, "Feyenoord": 0.86, "AZ": 0.84,
    # Süper Lig
    "Galatasaray": 0.85, "Fenerbahçe": 0.85, "Fenerbahce": 0.85,
    "Beşiktaş": 0.83, "Trabzonspor": 0.82,
    # Scottish PL
    "Celtic": 0.82, "Rangers": 0.80,
    # Greek / Belgian / Other mid-European
    "Panathinaikos": 0.80, "Olympiakos": 0.80, "Anderlecht": 0.82,
    "Club Brugge": 0.83,
    # Argentina (Liga Profesional)
    "River Plate": 0.80, "Boca Juniors": 0.80, "Racing Club": 0.78,
    "Independiente": 0.76, "Estudiantes de La Plata": 0.76,
    "Huracán": 0.75, "San Lorenzo": 0.75, "Vélez": 0.75,
    # Brasil (Série A)
    "Flamengo": 0.80, "Palmeiras": 0.80, "Fluminense": 0.80,
    "Internacional": 0.79, "Atlético Mineiro": 0.79, "Botafogo": 0.78,
    "São Paulo": 0.78, "Santos": 0.78, "Corinthians": 0.78,
    "Grêmio": 0.77, "Cruzeiro": 0.76, "Vasco": 0.75,
    "Red Bull Bragantino": 0.78,
    # Liga MX
    "Club América": 0.78, "Tigres": 0.78, "Tigres UANL": 0.78,
    "Monterrey": 0.78, "CF Monterrey": 0.78, "Cruz Azul": 0.77,
    "Guadalajara": 0.77, "Chivas": 0.77, "Pumas": 0.76, "Pachuca": 0.76,
    # MLS
    "Inter Miami": 0.75, "LA Galaxy": 0.75, "NYCFC": 0.75,
    "Seattle Sounders": 0.74, "Portland Timbers": 0.74, "Atlanta United": 0.75,
    "New England Revolution": 0.73, "Columbus Crew": 0.73,
    "Real Salt Lake": 0.73, "Minnesota United": 0.73,
    "Sporting Kansas City": 0.73, "Vancouver Whitecaps": 0.74,
    # Saudi Pro League
    "Al-Hilal": 0.70, "Al-Nassr": 0.70, "Al-Ittihad": 0.70,
    "Al-Ahli": 0.70, "Al-Qadsiah": 0.68, "Al-Shabab": 0.68,
    "Al-Fateh": 0.67, "Al-Ain": 0.67,
    # J1 League (Japón)
    "Urawa Red Diamonds": 0.72, "Kashima Antlers": 0.72,
    "Vissel Kobe": 0.72, "Kawasaki Frontale": 0.72,
    "Gamba Osaka": 0.70, "Cerezo Osaka": 0.70,
    # K League (Corea)
    "Jeonbuk": 0.70, "Ulsan": 0.70, "Suwon": 0.68,
    # A-League (Australia/NZ)
    "Melbourne City": 0.68, "Sydney FC": 0.68, "Wellington Phoenix": 0.65,
    "Western United": 0.65,
    # Ligas asiáticas / menores
    "Selangor": 0.55, "Johor Darul Ta'zim": 0.57, "Selangor FC": 0.55,
    "Al-Sadd": 0.60, "Al-Duhail": 0.60, "Al-Rayyan": 0.58,
    "Foolad": 0.62, "Persepolis": 0.62, "Esteghlal": 0.62,
    "Nassaji": 0.60, "Zob Ahan": 0.60,
    # Russian Premier League
    "Zenit": 0.78, "CSKA": 0.78, "Spartak": 0.77, "Lokomotiv": 0.76,
    "Krasnodar": 0.77, "Dynamo Moscow": 0.76, "Rostov": 0.75,
    "Rubin Kazan": 0.74, "Akhmat": 0.73,
    # ── Fix nombres (mismatches detectados) ──────────────────────────────────
    "Bayer 04 Leverkusen": 1.00,   # era "Bayer Leverkusen"
    "Al Duhail": 0.60,             # era "Al-Duhail"
    "New York City FC": 0.75,      # era "NYCFC"
    "Inter Miami CF": 0.75,        # variante nombre
    "Olympiacos FC": 0.80,         # era "Olympiakos"
    "Olympiakos FC": 0.80,
    # ── Premier League extras ─────────────────────────────────────────────────
    "Fulham": 0.96, "Bournemouth": 0.96, "Ipswich Town": 0.95,
    "Southampton": 0.95, "Burnley": 0.94, "Luton Town": 0.93,
    # ── Championship (England) ───────────────────────────────────────────────
    "Leeds United": 0.84, "Sunderland": 0.84, "Sheffield United": 0.83,
    "Norwich City": 0.83, "Derby County": 0.82, "Coventry City": 0.82,
    "Watford": 0.82, "Middlesbrough": 0.82, "Hull City": 0.82,
    "Millwall": 0.81, "Swansea City": 0.81, "Cardiff City": 0.80,
    "Stoke City": 0.80, "Birmingham City": 0.80, "Wrexham": 0.80,
    "Rotherham United": 0.78, "Plymouth Argyle": 0.78, "Portsmouth": 0.78,
    "Barnsley": 0.76, "Peterborough United": 0.77,
    "Preston North End": 0.79, "Braintree Town": 0.68,
    "Port Vale": 0.74, "Swindon Town": 0.72,
    # ── Bundesliga extras ────────────────────────────────────────────────────
    "VfL Wolfsburg": 0.94, "1. FSV Mainz 05": 0.93, "Borussia M'gladbach": 0.93,
    "FC St. Pauli": 0.91, "1. FC Union Berlin": 0.92, "Holstein Kiel": 0.90,
    "Hamburger SV": 0.88, "Hannover 96": 0.87, "FC Schalke 04": 0.87,
    "Fortuna Düsseldorf": 0.87, "Karlsruher SC": 0.85,
    # ── LaLiga extras ────────────────────────────────────────────────────────
    "Mallorca": 0.91, "Celta Vigo": 0.90, "Rayo Vallecano": 0.90,
    "Espanyol": 0.90, "Valencia": 0.90, "Levante UD": 0.88,
    "Granada": 0.87, "Elche": 0.85, "CD Castellón": 0.82,
    # ── Serie A extras ───────────────────────────────────────────────────────
    "Bologna": 0.94, "Torino": 0.92, "Udinese": 0.91, "Cagliari": 0.91,
    "Genoa": 0.91, "Hellas Verona": 0.90, "Como": 0.90, "Venezia": 0.90,
    "Parma": 0.90, "Sassuolo": 0.89, "Frosinone": 0.87,
    "Sampdoria": 0.86, "Cremonese": 0.85,
    # ── Ligue 1 extras ───────────────────────────────────────────────────────
    "Nice": 0.92, "Stade Rennais": 0.91, "Toulouse": 0.89,
    "Stade de Reims": 0.89, "RC Strasbourg": 0.89, "Nantes": 0.88,
    "Auxerre": 0.87, "Le Havre": 0.87, "Montpellier": 0.87,
    "Saint-Étienne": 0.87, "Paris FC": 0.86, "Lorient": 0.85,
    "Bastia": 0.83, "Sochaux": 0.82, "Nancy": 0.81,
    # ── Primeira Liga extras ─────────────────────────────────────────────────
    "Vizela": 0.80, "Gil Vicente": 0.80, "Vitória SC": 0.80,
    "Vitória de Setúbal": 0.78, "Casa Pia": 0.78, "Chaves": 0.78,
    "CF Estrela Amadora": 0.77, "SC Farense": 0.76, "Torreense": 0.75,
    # ── Eredivisie extras ────────────────────────────────────────────────────
    "FC Twente": 0.84, "Sparta Rotterdam": 0.81, "NEC Nijmegen": 0.82,
    "PEC Zwolle": 0.81, "RKC Waalwijk": 0.80, "Heracles Almelo": 0.80,
    "FC Volendam": 0.80, "Almere City FC": 0.79, "FC Den Bosch": 0.76,
    "Jong FC Utrecht": 0.75, "VVV-Venlo": 0.75, "SC Telstar": 0.73,
    # ── Belgian Pro League extras ────────────────────────────────────────────
    "KRC Genk": 0.83, "Royale Union Saint-Gilloise": 0.83,
    "KAA Gent": 0.82, "Royal Antwerp FC": 0.82, "Standard Liège": 0.82,
    "RC Sporting Charleroi": 0.80, "KV Mechelen": 0.80, "Cercle Brugge": 0.80,
    "SV Zulte Waregem": 0.78, "Sint-Truidense VV": 0.78,
    "FCV Dender": 0.76, "SK Beveren": 0.76,
    # ── Swiss SL ─────────────────────────────────────────────────────────────
    "BSC Young Boys": 0.84, "Red Bull Salzburg": 0.84,
    "FC Zürich": 0.82, "Servette FC": 0.81, "FC St. Gallen 1879": 0.80,
    "FC Lugano": 0.79, "Stade Nyonnais": 0.73,
    # ── Czech / Slovak ───────────────────────────────────────────────────────
    "SK Slavia Praha": 0.82, "AC Sparta Praha": 0.82,
    "FC Viktoria Plzeň": 0.80, "FC Slovan Liberec": 0.76,
    "FC Hradec Králové": 0.74, "ŠK Slovan Bratislava": 0.80,
    "1. FC Tatran Prešov": 0.72,
    # ── Austrian BL ──────────────────────────────────────────────────────────
    "FK Austria Wien": 0.80, "LASK": 0.79, "Wolfsberger AC": 0.77,
    # ── Scandinavian ─────────────────────────────────────────────────────────
    "FC Midtjylland": 0.82, "FC København": 0.82, "Brøndby IF": 0.81,
    "FC Nordsjælland": 0.79, "Silkeborg IF": 0.78, "AGF": 0.77,
    "Randers FC": 0.76, "Bodø/Glimt": 0.80, "Molde FK": 0.78,
    "Viking FK": 0.78, "Strømsgodset": 0.75, "Sarpsborg 08": 0.75,
    "Malmö FF": 0.80, "IFK Norrköping": 0.77, "Mjällby AIF": 0.74,
    # ── Scottish PL extras ───────────────────────────────────────────────────
    "Hibernian": 0.78, "Heart of Midlothian": 0.78,
    "Kilmarnock": 0.77, "Motherwell": 0.75, "Shamrock Rovers": 0.76,
    # ── Croatian / Slovenian / Serbian ───────────────────────────────────────
    "GNK Dinamo Zagreb": 0.82, "HNK Hajduk Split": 0.79,
    "HNK Rijeka": 0.78, "FK Crvena zvezda": 0.82,
    "NK Maribor": 0.76, "NK Slaven Belupo": 0.73,
    "FK TSC Bačka Topola": 0.76,
    # ── Greek extras ─────────────────────────────────────────────────────────
    "PAOK": 0.80, "AEK Athens": 0.80, "APS Atromitos Athinon": 0.76,
    "AE Kifisia": 0.72,
    # ── Turkish SL extras ────────────────────────────────────────────────────
    "Başakşehir FK": 0.82, "Çaykur Rizespor": 0.79, "Alanyaspor": 0.79,
    "Samsunspor": 0.79, "Konyaspor": 0.78, "Kasımpaşa": 0.78,
    "Kayserispor": 0.77, "Iğdır FK": 0.72,
    # ── Hungarian / Romanian / Bulgarian ─────────────────────────────────────
    "Ferencváros TC": 0.80, "Puskás Akadémia": 0.75, "ETO FC Győr": 0.73,
    "FCSB": 0.77, "FC Universitatea Cluj": 0.74,
    "Ludogorets": 0.78, "PFK Montana 1921": 0.68,
    # ── Cypriot / Israeli ────────────────────────────────────────────────────
    "APOEL Nicosia": 0.76, "Apollon Limassol": 0.75, "Omonia Nicosia": 0.75,
    "AEL Limassol": 0.74, "AEL Novibet": 0.74, "AEK Larnaca": 0.74,
    "Aris Limassol": 0.73, "Pafos FC": 0.74,
    "Maccabi Haifa": 0.78, "Maccabi Tel Aviv": 0.78, "Hapoel Ironi Kiryat Shmona": 0.74,
    # ── Polish / Finnish ─────────────────────────────────────────────────────
    "Jagiellonia Białystok": 0.78, "KS Lechia Gdańsk": 0.76,
    "Cracovia": 0.76, "Pogoń Szczecin": 0.76, "Wisła Płock": 0.75,
    "Widzew Łódź": 0.75, "SJK": 0.72,
    # ── MLS extras ───────────────────────────────────────────────────────────
    "Los Angeles FC": 0.75, "Philadelphia Union": 0.74,
    "Nashville SC": 0.74, "Orlando City SC": 0.74, "Charlotte FC": 0.74,
    "San Diego FC": 0.74, "New York Red Bulls": 0.74,
    "Vancouver Whitecaps FC": 0.74, "FC Cincinnati": 0.74,
    "Colorado Rapids": 0.73, "DC United": 0.73,
    "FC Dallas": 0.73, "Nashville SC": 0.74, "Chicago Fire": 0.73,
    "Toronto FC": 0.73, "Miami FC": 0.68,
    # ── Liga MX extras ───────────────────────────────────────────────────────
    "CD Toluca": 0.76, "Club Tijuana": 0.75, "Atlas FC": 0.75,
    "Club León": 0.76, "FC Juárez": 0.74,
    # ── Sudamérica extras ────────────────────────────────────────────────────
    "CA Talleres": 0.75, "CA Lanús": 0.75, "Rosario Central": 0.75,
    "LDU": 0.73, "Universidad Católica del Ecuador": 0.70,
    "Universidad de Chile": 0.70, "Universidad de Concepción": 0.66,
    "Cobresal": 0.65, "Cerro Porteño": 0.73, "Olimpia": 0.71,
    "Deportivo Saprissa": 0.70, "Academia Puerto Cabello": 0.60,
    # ── África ───────────────────────────────────────────────────────────────
    "Al Ahly FC": 0.72, "Zamalek SC": 0.70, "Pyramids FC": 0.68,
    "ENPPI": 0.66, "El Gouna FC": 0.64, "ZED FC": 0.63,
    "Espérance Tunis": 0.70, "Club Africain": 0.67,
    "Stade Tunisien": 0.65, "AS FAR Rabat": 0.70, "RS Berkane": 0.68,
    "USM Alger": 0.67, "ASO Chlef": 0.63,
    "Orlando Pirates": 0.68, "Mamelodi Sundowns": 0.70,
    "Kaizer Chiefs": 0.66, "Polokwane City": 0.64, "Siwelele FC": 0.62,
    "Accra Hearts of Oak": 0.64, "Violette AC": 0.60,
    # ── Medio Oriente extras ─────────────────────────────────────────────────
    "Al-Wakrah": 0.58, "Al-Arabi SC": 0.58, "Al Shamal SC": 0.57,
    "Al-Gharafa": 0.60, "Qatar SC": 0.57, "Al-Sailiya": 0.57,
    "Al-Hussein Irbid": 0.60, "Al-Wehdat": 0.62, "Al Faisaly SC": 0.60,
    "Al-Shorta": 0.60, "Al-Zawraa": 0.60, "Zakho SC": 0.58,
    "Al-Nasr Dubai": 0.62, "Al-Wahda FC": 0.62, "Baniyas": 0.61,
    "Al-Sharjah": 0.61, "Al Bataeh": 0.58, "Dibba Al-Fujairah": 0.57,
    "Al-Ettifaq": 0.70, "Al-Fayha": 0.67, "Al-Riyadh": 0.66,
    "Al Orobah": 0.65, "Al Ula": 0.62, "Neom SC": 0.63, "Abha": 0.65,
    "Al-Najma SC": 0.60, "Al-Shahaniya": 0.57,
    # ── Iran extras ──────────────────────────────────────────────────────────
    "Tractor FC": 0.62, "Sepahan S.C.": 0.62,
    "Malavan Bandar Anzali FC": 0.60, "Sanat Naft Abadan": 0.60,
    "Zob Ahan": 0.60,
    # ── Uzbekistán extras ────────────────────────────────────────────────────
    "Pakhtakor Tashkent": 0.62, "Neftchi Fergana": 0.59,
    "FC Buxoro": 0.58, "Nasaf Qarshi": 0.59, "Dinamo Samarqand": 0.58,
    "Surkhon Termez": 0.57, "FC OKMK": 0.58, "Navbahor Namangan": 0.59,
    # ── Asia del Este extras ─────────────────────────────────────────────────
    "FC Tokyo": 0.70, "Albirex Niigata": 0.68, "Sanfrecce Hiroshima": 0.70,
    "Daejeon Hana Citizen": 0.68, "Gangwon FC": 0.68, "FC Seoul": 0.68,
    "Zhejiang": 0.63, "Persib Bandung": 0.58, "Port FC": 0.62,
    # ── Kazajistán / Armenia / Azerbaiyán ────────────────────────────────────
    "Astana": 0.65, "FC Noah": 0.63, "Turan Tovuz": 0.63,
    # ── Oceanía extras ───────────────────────────────────────────────────────
    "Auckland FC": 0.65, "Western Sydney Wanderers": 0.66,
    "Brisbane Roar": 0.66, "Melbourne Victory": 0.67,
    # ── Restantes ────────────────────────────────────────────────────────────
    "SV Werder Bremen": 0.94,
    "Pisa": 0.86, "Cultural Leonesa": 0.79, "Tondela": 0.76,
    "Colorado Springs Switchbacks FC": 0.68, "Phoenix Rising FC": 0.68,
    "Pari Nizhny Novgorod": 0.75, "Dinamo Makhachkala": 0.72,
    "Akron Togliatti": 0.74,
    "Etoile Sportive Du Sahel": 0.67, "Avenir Sportif De La Marsa": 0.63,
    "US Ben Guerdane": 0.62,
    "CD Marathon": 0.65, "Persis Solo": 0.58,
    "Panama U20": 0.55,
}
_CLUB_Q_DEFAULT = 0.85   # clubes desconocidos → asumimos nivel medio-europeo

# Rankings FIFA aproximados para selecciones que no clasificaron al Mundial 2026.
# Misma escala que fifa_rank_score en wc2026_team_stats.json (0-100).
_FIFA_RANK_EXT = {
    "Italy": 72, "Denmark": 68, "Poland": 55, "Romania": 50, "Hungary": 45,
    "Greece": 42, "Iceland": 38, "Slovakia": 40, "Albania": 36, "Slovenia": 38,
    "Serbia": 55, "Ukraine": 60, "Kosovo": 25, "North Macedonia": 30, "Malta": 12,
    "Cyprus": 18, "Kazakhstan": 22, "Armenia": 25, "Georgia": 30, "Azerbaijan": 20,
    "Belarus": 22, "Estonia": 18, "Latvia": 16, "Lithuania": 15, "Moldova": 12,
    "Faroe Islands": 10, "Gibraltar": 5, "San Marino": 3, "Liechtenstein": 8,
    "Luxembourg": 20, "Andorra": 8, "Finland": 35, "Bulgaria": 28,
    "Russia": 45, "Turkey": 45,
    "Peru": 42, "Venezuela": 35, "Chile": 42,
    "Jamaica": 30, "Trinidad and Tobago": 22, "El Salvador": 25,
    "Honduras": 28, "Guatemala": 22, "Barbados": 12, "Bermuda": 10,
    "Mali": 35, "Burkina Faso": 30, "Guinea": 32, "Tanzania": 22,
    "Angola": 28, "Zimbabwe": 20, "Uganda": 22, "Kenya": 20, "Zambia": 25,
    "Rwanda": 18, "Mozambique": 18, "Benin": 22, "Guinea-Bissau": 18,
    "Djibouti": 8, "Comoros": 18, "Namibia": 16, "Gabon": 22,
    "United Arab Emirates": 30, "UAE": 30, "Kuwait": 22, "Bahrain": 22,
    "Oman": 20, "Vietnam": 18, "Thailand": 20, "Tajikistan": 18,
    "Kyrgyzstan": 15, "Turkmenistan": 12, "North Korea": 15, "India": 18,
    "China PR": 25, "Philippines": 15, "Myanmar": 12,
    "Fiji": 12, "Vanuatu": 8, "Papua New Guinea": 10, "Solomon Islands": 10,
}


def club_quality(club_name: str) -> float:
    """Coeficiente de calidad de liga para ajustar xg/xa del club."""
    if not club_name:
        return _CLUB_Q_DEFAULT
    for key, val in _CLUB_Q.items():
        if key.lower() in club_name.lower():
            return val
    return _CLUB_Q_DEFAULT


def compute_intl_schedules(match_analytics: dict, team_stats: dict) -> dict:
    """
    Para cada selección, calcula la calidad de sus rivales internacionales
    usando un promedio PONDERADO por la calidad del rival (FIFA ranking).
    Rivales fuertes pesan exponencialmente más que rivales débiles:
    weight = fifa_score^1.5  →  Francia(95) pesa 15× más que Puerto Rico(8).
    Así los amistosos contra rivales muy débiles casi no mueven la aguja.
    Retorna {team: quality_multiplier} en [0.60, 0.92].
    """
    # Lookup comprehensivo: primero WC teams (precisos), luego extended
    fifa = {}
    fifa.update(_FIFA_RANK_EXT)                                  # base (no-WC)
    fifa.update({n: d["fifa_rank_score"] for n, d in team_stats.items()})  # WC teams sobreescriben

    Q_MAX, Q_MIN = 0.92, 0.60
    OPP_MAX, OPP_MIN = 75, 12

    def lookup(opp_name):
        """Devuelve el FIFA score real del rival; None si no se encuentra."""
        if opp_name in fifa:
            return fifa[opp_name]
        opp_lower = opp_name.lower()
        for k, v in fifa.items():
            if k and (k.lower() in opp_lower or opp_lower in k.lower()):
                return v
        return None

    result = {}
    for team, data in match_analytics.items():
        w_sum, w_total = 0.0, 0.0
        for m in data.get("matches", []):
            score = lookup(m.get("opponent", ""))
            if score is None:
                score = 20   # rival desconocido → asumir débil
            w = score ** 1.5   # peso exponencial: rivales fuertes dominan
            w_sum   += score * w
            w_total += w
        avg = w_sum / w_total if w_total > 0 else 30
        q = Q_MIN + (avg - OPP_MIN) / (OPP_MAX - OPP_MIN) * (Q_MAX - Q_MIN)
        result[team] = round(max(Q_MIN, min(Q_MAX, q)), 3)

    return result


# Override manual para arqueros titulares confirmados (player_id de SofaScore)
GK_STARTER_OVERRIDES = {
    "Germany":   8959,    # Manuel Neuer
    "Argentina": 158263,  # Emiliano 'Dibu' Martínez (Aston Villa)
    "Sweden":    561430,  # Viktor Johansson
    "Paraguay":  991709,  # Orlando Gill
}

# Set piece bonuses (additive to xG/90 or xA/90)
SP_BONUS = {
    "pk_primary":   {"xg": 0.12, "xa": 0.00},
    "pk_secondary": {"xg": 0.06, "xa": 0.00},
    "fk_primary":   {"xg": 0.03, "xa": 0.05},
    "fk_secondary": {"xg": 0.01, "xa": 0.02},
    "ck_primary":   {"xg": 0.00, "xa": 0.05},
}

# ── Pesos de blend ────────────────────────────────────────────────────────────
CLUB_WEIGHT   = 0.70   # peso stats de club 2024-25
INTL_WEIGHT   = 0.30   # peso stats internacionales (clasificatorias, etc.)
FORM_WEIGHT   = 0.62   # peso forma WC F1/F2/F3 — aumentado post grupo completo (era 0.45)
SEASON_WEIGHT = 1.0 - FORM_WEIGHT  # 0.55

MIN_INTL_GAMES = 3     # mínimo de partidos internacionales para usar blend; si no, solo club
MIN_CLUB_MINS  = 200   # mínimo mins de club para stats confiables

# Bayesian shrinkage (igual que LPF)
K_CLUB = 8    # partidos para 50/50 en xG regresado (club)
K_INTL = 12   # más regresión porque contexto intl es menos frecuente
K_XA   = 8

# ── Scoring Fantasy Manager (mismo que LPF) ───────────────────────────────────
FM = {
    "goal":         {"G": 10, "D": 8, "M": 6, "F": 5},
    "assist":       3,
    "cs":           {"G": 4, "D": 3, "M": 1, "F": 0},
    "mins":         2,
    "yellow":      -1,
    "red":         -3,
    "winning_goal": 3,
    "save_per_3":   1,   # cada 3 atajadas = 1 pt
}

LEAGUE_AVG_GC_PG = 0.90   # promedio global goles contra / partido en selecciones

# Override de arquetipo táctico (no cambia la posición, cambia cómo se proyecta vs rival)
# Usar cuando el jugador tiene un rol táctico distinto al que sugieren sus stats históricas.
# Los tipos "wide_mid" / "shadow_striker" etc. ajustan qué vulnerabilidad del rival se activa.
PLAYER_TYPE_OVERRIDES = {
    1019322: "wide_mid",   # Florian Wirtz (Germany) — volante/extremo izquierdo en WC
}

# Override de posición según Fantasy Manager AR (fuente de verdad para scoring)
POSITION_OVERRIDES = {
    259117: "M",   # Joshua Kimmich (Germany) — FM=VOL
    929193: "M",   # Maximiliano Araújo (Uruguay) — FM=MED/VOL (no D)
    124712: "M",   # Neymar (Brazil) — FM=M
    # Algeria
    1094482: "M",   # Adil Boulbina — FM=VOL
    1218066: "D",   # Anis Hadj Moussa — FM=DEF
    1407524: "M",   # Ibrahim Maza
    1103488: "D",   # Rafik Belghali
    158213:  "F",   # Riyad Mahrez
    # Australia
    307082:  "F",   # Awer Mabil
    907217:  "D",   # Jacob Italiano
    1118467: "F",   # Nishan Velupillay
    # Austria
    987504:  "M",   # Patrick Wimmer — FM=VOL
    # Belgium
    960441:  "M",   # Charles De Ketelaere
    823631:  "F",   # Dodi Lukébakio
    934386:  "F",   # Jérémy Doku
    # Bosnia & Herzegovina
    1425366: "F",   # Kerim Alajbegovic
    # Brazil
    1035995: "F",   # Luiz Henrique
    831005:  "F",   # Raphinha
    1464966: "F",   # Rayan
    1134200: "D",   # Wesley
    # Cabo Verde
    787429:  "F",   # Garry Rodrigues
    1094395: "F",   # Hélio Varela
    52797:   "F",   # Ryan Mendes
    1035280: "F",   # Telmo Arcanjo
    889052:  "F",   # Willy Semedo
    # Canada
    902083:  "F",   # Liam Millar
    1411145: "M",   # Niko Sigur
    973290:  "F",   # Tajon Buchanan
    # Colombia
    1160386: "F",   # Andrés Gómez
    870360:  "D",   # Daniel Muñoz
    877299:  "F",   # Jáminton Campaz
    883537:  "F",   # Luis Díaz
    # Croatia
    38710:   "F",   # Ivan Perišić
    1066802: "D",   # Marco Pašalić — FM=DEF
    # Czechia
    957604:  "M",   # Pavel Sulc
    # Côte d'Ivoire
    1568123: "F",   # Bazoumana Touré
    1030459: "F",   # Parfait Guiagon
    1110842: "F",   # Simon Adingra
    # DR Congo
    862078:  "M",   # Meschack Elia
    963399:  "F",   # Nathanaël Mbuku
    344953:  "F",   # Théo Bongonda
    # Ecuador
    881844:  "D",   # Angelo Preciado
    937937:  "F",   # Gonzalo Plata
    1116571: "F",   # Nilson Angulo
    805465:  "D",   # Pervis Estupiñán
    # Egypt
    942836:  "F",   # Haissem Hassan
    1008171: "F",   # Ibrahim Adel
    295361:  "F",   # Mahmoud Trezeguet
    159665:  "F",   # Mohamed Salah
    547494:  "F",   # Zizo
    # England
    966547:  "F",   # Noni Madueke
    # France
    1130939: "F",   # Maghnes Akliouche
    978838:  "F",   # Michael Olise
    # Germany
    990201:  "F",   # Jamie Leweling
    293519:  "F",   # Leroy Sané
    # Ghana
    934354:  "F",   # Antoine Semenyo
    1138352: "M",   # Augustine Boakye
    1477662: "F",   # Christopher Baah
    1103589: "F",   # Issahaku Fatawu
    783374:  "F",   # Iñaki Williams
    # Haiti
    1002387: "M",   # Carl Sainté
    1035986: "F",   # Josué Casimir
    954066:  "F",   # Ruben Providence
    # Iran
    1170977: "D",   # Arya Yousefi
    881182:  "F",   # Mehdi Ghayedi
    786133:  "D",   # Ramin Rezaeian
    828230:  "M",   # Roozbeh Cheshmi
    # Iraq
    1101887: "F",   # Ahmed Qasem
    1066729: "F",   # Ali Jasim
    1026519: "F",   # Marko Farji
    1106352: "F",   # Youssef Amyn
    # Japan
    783278:  "F",   # Junya Ito
    905352:  "F",   # Keito Nakamura
    790965:  "F",   # Ritsu Doan
    880218:  "F",   # Takefusa Kubo
    1020422: "F",   # Yuito Suzuki
    # Jordan
    812997:  "D",   # Ehsan Haddad
    812557:  "F",   # Mahmoud Al-Mardi
    # Mexico
    905257:  "F",   # César Huerta
    944068:  "M",   # Érik Lira
    # Morocco
    1011375: "F",   # Abde Ezzalzouli
    835485:  "F",   # Brahim Díaz
    1142675: "F",   # Chemsdine Talbi
    1638338: "F",   # Gessime Yassine
    # Netherlands
    862967:  "F",   # Cody Gakpo
    917005:  "F",   # Crysencio Summerville
    759520:  "D",   # Denzel Dumfries
    851596:  "F",   # Justin Kluivert
    # New Zealand
    1122425: "D",   # Ben Old
    905267:  "F",   # Elijah Just
    # Norway
    800951:  "D",   # Julian Ryerson
    934409:  "D",   # Marcus Pedersen
    1065216: "F",   # Oscar Bobb
    # Panama
    83951:   "F",   # Alberto Quintero
    1217929: "F",   # Azarias Londoño
    1021117: "F",   # César Yanis
    796328:  "F",   # Ismael Díaz
    842253:  "F",   # José Luis Rodríguez
    833352:  "F",   # Yoel Bárcenas
    # Paraguay
    988656:  "F",   # Gustavo Caballero
    # Portugal
    280979:  "F",   # Gonçalo Guedes
    879349:  "F",   # Pedro Neto
    # Qatar
    936542:  "F",   # Ahmed Al-Ganehi
    794541:  "F",   # Akram Afif
    796501:  "F",   # Almoez Ali
    797734:  "F",   # Edmílson Junior
    # Saudi Arabia
    1130539: "D",   # Ayman Yahya
    1804369: "D",   # Mohammed Abu Al-Shamat
    160893:  "F",   # Salem Al-Dawsari
    966849:  "D",   # Saud Abdulhamid
    # Scotland
    1154861: "F",   # Ben Gannon-Doak
    1489210: "F",   # Findlay Curtis
    # Senegal
    914309:  "F",   # Iliman Ndiaye
    217704:  "F",   # Sadio Mané
    # South Africa
    1210653: "D",   # K. Sebelebele
    984505:  "F",   # Oswin Appollis
    1564998: "F",   # Relebohile Mofokeng
    1179164: "F",   # Thapelo Maseko
    1101745: "F",   # Tshepang Moremi
    # South Korea
    1002508: "F",   # Ji-sung Eom
    917087:  "F",   # Kang-in Lee
    # Spain
    177177:  "D",   # Alejandro Grimaldo
    1402912: "F",   # Lamine Yamal
    1085400: "F",   # Nico Williams
    910031:  "F",   # Álex Baena
    # Sweden
    918517:  "F",   # Benjamin Nygren — FM=DEL
    1021272: "D",   # Daniel Svensson
    319847:  "D",   # Ken Sema
    # Switzerland
    944327:  "F",   # Dan Ndoye
    798303:  "D",   # Miro Muheim
    872919:  "F",   # Rubén Vargas
    157377:  "D",   # Silvan Widmer
    # Tunisia
    945204:  "F",   # Elias Achouri
    1113488: "F",   # Ismaël Gharbi
    919225:  "F",   # Mortadha Ben Ouanes
    957143:  "F",   # Sebastian Tounekti
    # Türkiye
    904096:  "F",   # Barış Alper Yılmaz
    138152:  "M",   # Kaan Ayhan
    999396:  "F",   # Oğuz Aydın
    857738:  "F",   # Yunus Akgün
    226986:  "F",   # İrfan Can Kahveci
    # USA
    1471659: "F",   # Max Arfsten
    855810:  "F",   # Timothy Weah
    790108:  "F",   # Álex Zendejas
    # Uruguay
    932233:  "F",   # Brian Rodríguez
    989803:  "F",   # Facundo Pellistri
    966575:  "M",   # Rodrigo Zalazar
    # Uzbekistan
    1118429: "F",   # Abbosbek Fayzullaev
    871965:  "F",   # Azizbek Amanov
    358880:  "F",   # Dostonbek Khamdamov
    333611:  "F",   # Jaloliddin Masharipov
    985882:  "F",   # Oston Urunov
    # Curaçao
    1219978: "F",   # Jeremy Antonisse
    892867:  "F",   # Kenji Gorré
    863208:  "F",   # Sontje Hansen
    860282:  "F",   # Brandley Kuwas
    876474:  "F",   # Jearl Margaritha
    1004277: "F",   # Ar'jany Martha
    1036004: "F",   # Jearl Margaritha (alt ID)
    1092638: "F",   # Jeremy Antonisse (alt ID)
    1199057: "F",   # Sontje Hansen (alt ID)
    796142:  "F",   # Kenji Gorré (alt ID)
    252885:  "F",   # Brandley Kuwas (alt ID)
    # Argentina / Uruguay
    158263:  "G",   # Emiliano 'Dibu' Martínez (Argentina GK — Aston Villa)
    973533:  "M",   # Emiliano Martínez (Uruguay MED — distinto de Dibu id=158263)
    # Jordan
    1114775: "D",   # Mohannad Taha
    # Mexico
    1023088: "D",   # Jorge Gutiérrez
    # Sweden GK (remove wrong M override — es arquero)
    # 561430 Viktor Johansson → G por raw position, sin override
}

# Auto-cargar wide_mid desde detección por cruces reales del Mundial
# infer_wide_players.py genera este archivo analizando totalCross en los lineups F1/F2/F3.
# Solo se aplica si:
#   a) avg_crosses >= 2.5 (señal suficiente de juego por banda)
#   b) el jugador NO tiene POSITION_OVERRIDES "F" o "D" (ya tiene posición correcta)
#   c) no existe ya un entry manual en PLAYER_TYPE_OVERRIDES
_wide_det_path = BASE_DIR / "wide_players_detected.json"
if _wide_det_path.exists():
    import json as _json
    _wd = _json.load(open(_wide_det_path, encoding="utf-8"))
    for _cand in _wd.get("wide_mid_candidates", []):
        _pid = _cand["pid"]
        if (_pid not in PLAYER_TYPE_OVERRIDES
                and POSITION_OVERRIDES.get(_pid) not in ("F", "D")):
            PLAYER_TYPE_OVERRIDES[_pid] = "wide_mid"

# BPR: 3 pts al mejor rating, 2 al segundo, 1 al tercero (por partido, según SofaScore)
BPR_POINTS  = [3, 2, 1]
BPR_SIGMA   = 0.40   # dispersión de ratings SofaScore (~0.4 pts de std entre partidos)


def load_data(fecha_filter=None):
    with open(PLAYER_PATH, encoding="utf-8") as f:
        players_raw = json.load(f)
    with open(TEAM_PATH, encoding="utf-8") as f:
        team_stats = json.load(f)
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures_data = json.load(f)

    form_data = {}
    if FORM_PATH.exists():
        with open(FORM_PATH, encoding="utf-8") as f:
            form_data = json.load(f)
        with_form = sum(1 for v in form_data.values() if v.get("form"))
        print(f"[form] {with_form}/{len(form_data)} jugadores con forma de selección")

    lineups = {}
    if LINEUPS_PATH.exists():
        with open(LINEUPS_PATH, encoding="utf-8") as f:
            lineups = json.load(f)
        confirmed_matches = sum(1 for v in lineups.values() if v.get("confirmed"))
        print(f"[lineups] {len(lineups)} partidos cargados  ({confirmed_matches} confirmados)")


    setpieces = {}
    if SETPIECES_PATH.exists():
        with open(SETPIECES_PATH, encoding="utf-8") as f:
            setpieces = json.load(f)
        print(f"[setpieces] {len(setpieces)} selecciones cargadas")

    predictions = {}
    if PREDICTIONS_PATH.exists():
        with open(PREDICTIONS_PATH, encoding="utf-8") as f:
            predictions = json.load(f)
        print(f"[predictions] {len(predictions.get('fixtures', []))} partidos con modelo Dixon-Coles")

    coaches = {}
    if COACHES_PATH.exists():
        with open(COACHES_PATH, encoding="utf-8") as f:
            coaches = json.load(f)
        print(f"[coaches] {len(coaches)} DTs cargados")

    match_analytics = {}
    if MATCH_ANALYTICS_PATH.exists():
        with open(MATCH_ANALYTICS_PATH, encoding="utf-8") as f:
            match_analytics = json.load(f)

    # Fixtures: agrupar por round_num
    all_fixtures = fixtures_data.get("fixtures", [])
    # round_num: 1, 2, 3 dentro de la fase de grupos
    if fecha_filter:
        all_fixtures = [f for f in all_fixtures if f.get("round_num") == fecha_filter]

    wc_results = {}
    if WC_RESULTS_PATH.exists():
        with open(WC_RESULTS_PATH, encoding="utf-8") as f:
            wc_results = json.load(f)
        n_wc = len(wc_results.get("matches", {}))
        n_profiles = len(wc_results.get("team_profiles", {}))
        print(f"[wc_results] {n_wc} partidos jugados  ({n_profiles} perfiles de equipo)")

    print(f"[fixtures] {len(all_fixtures)} partidos{'  (fecha '+str(fecha_filter)+')' if fecha_filter else ''}")
    return players_raw, team_stats, form_data, all_fixtures, lineups, setpieces, predictions, coaches, match_analytics, wc_results


def blend_xg90(club_xg90, club_games, intl_xg90, intl_games):
    """Blend ponderado de stats de club e internacionales."""
    if intl_games >= MIN_INTL_GAMES and intl_xg90 is not None:
        total = CLUB_WEIGHT * club_games + INTL_WEIGHT * intl_games
        if total == 0:
            return club_xg90
        return (CLUB_WEIGHT * club_xg90 * club_games +
                INTL_WEIGHT * intl_xg90 * intl_games) / total
    return club_xg90


def get_xg90(stats):
    if not stats:
        return 0.0
    mins = max(stats.get("Minutos Jugados") or 1, 1)
    xg   = stats.get("xG") or 0.0
    if xg == 0:
        shots = stats.get("Remates Totales") or 0
        xg    = shots * 0.095
    return xg / mins * 90


def get_xa90(stats):
    if not stats:
        return 0.0
    mins = max(stats.get("Minutos Jugados") or 1, 1)
    xa   = stats.get("xA") or 0.0
    if xa == 0:
        kp = stats.get("Pases Clave") or 0
        xa = kp * 0.08
    return xa / mins * 90


def regress_to_mean(xg90, xa90, games, pos, pos_avgs, k_xg=K_CLUB, k_xa=K_XA):
    avg  = pos_avgs.get(pos, {"xg_90": xg90, "xa_90": xa90})
    w_xg = games / (games + k_xg)
    w_xa = games / (games + k_xa)
    return (
        round(w_xg * xg90 + (1 - w_xg) * avg["xg_90"], 4),
        round(w_xa * xa90 + (1 - w_xa) * avg["xa_90"], 4),
        round(w_xg, 2),
    )


def compute_positional_averages(players_raw):
    from collections import defaultdict
    totals = defaultdict(lambda: {"xg": 0.0, "xa": 0.0, "mins": 0})
    for pid, p in players_raw.items():
        pos  = _pos_key(p.get("position", ""))
        cs   = p.get("club_stats") or {}
        mins = cs.get("Minutos Jugados") or 0
        if not pos or mins < 200:
            continue
        totals[pos]["xg"]   += cs.get("xG") or 0
        totals[pos]["xa"]   += cs.get("xA") or 0
        totals[pos]["mins"] += mins
    avgs = {}
    for pos, d in totals.items():
        m = max(d["mins"], 1)
        avgs[pos] = {"xg_90": round(d["xg"] / m * 90, 4),
                     "xa_90": round(d["xa"] / m * 90, 4)}
    return avgs


def _pos_key(raw_pos, player_id=None):
    if player_id is not None and int(player_id) in POSITION_OVERRIDES:
        return POSITION_OVERRIDES[int(player_id)]
    p = str(raw_pos or "").upper()
    if p in ("GOALKEEPER", "G", "GK"):       return "G"
    if p in ("DEFENDER", "D", "CB", "LB", "RB"): return "D"
    if p in ("MIDFIELDER", "M", "CM", "DM", "AM"): return "M"
    if p in ("FORWARD", "F", "ST", "LW", "RW", "ATTACKER"): return "F"
    return None


def team_defensive_profiles(players_raw):
    """box_vuln / wide_vuln por selección usando saves dentro/fuera del GK titular."""
    from collections import defaultdict
    gk_by_team = defaultdict(list)
    for pid, p in players_raw.items():
        if _pos_key(p.get("position",""), player_id=pid) == "G":
            gk_by_team[p.get("national_team","")].append(p)

    raw = {}
    for team, gks in gk_by_team.items():
        main = max(gks, key=lambda g: (g.get("intl_stats") or {}).get("Minutos Jugados") or 0)
        cs = (main.get("intl_stats") or main.get("club_stats") or {})
        si = cs.get("Atajadas Dentro") or 0
        so = cs.get("Atajadas Fuera")  or 0
        total = max(si + so, 1)
        raw[team] = {"box_ratio": si / total, "wide_ratio": so / total}

    avg_box  = sum(v["box_ratio"]  for v in raw.values()) / max(len(raw), 1)
    avg_wide = sum(v["wide_ratio"] for v in raw.values()) / max(len(raw), 1)

    profiles = {}
    for team, d in raw.items():
        bv = (d["box_ratio"]  - avg_box)  / max(avg_box,  0.01)
        wv = (d["wide_ratio"] - avg_wide) / max(avg_wide, 0.01)
        profiles[team] = {
            "box_vuln":  round(max(-1.0, min(1.0, bv)), 3),
            "wide_vuln": round(max(-1.0, min(1.0, wv)), 3),
        }
    return profiles


def classify_player_type(pos, xg_90, xa_90, shots_90, kp_90):
    if pos == "F":
        if xa_90 >= 0.14 and shots_90 < 2.2:          return "wide_fwd"
        if shots_90 >= 2.0 and xa_90 < 0.10:          return "box_striker"
        if shots_90 >= 1.7 and xa_90 >= 0.10:         return "complete_striker"
        if xg_90 >= 0.25 and shots_90 < 1.5:          return "poacher"
        return "pressing_fwd"
    elif pos == "M":
        if shots_90 >= 2.0 and xg_90 >= 0.20:         return "shadow_striker"
        if xa_90 >= 0.22:                              return "playmaker"
        if xg_90 >= 0.10 and xa_90 >= 0.10:           return "attacking_mid"
        if xa_90 >= 0.13 and kp_90 >= 1.3:            return "creative_mid"
        if xg_90 >= 0.12:                              return "goalscoring_mid"
        if xg_90 < 0.05 and xa_90 < 0.07:             return "cdm"
        return "box_to_box"
    elif pos == "D":
        if xa_90 >= 0.10 or (kp_90 >= 1.5 and xa_90 >= 0.06): return "overlapping_def"
        if xa_90 >= 0.06 or xg_90 >= 0.08:            return "attacking_def"
        return "defender"
    return "other"


def get_type_mult(player_type, opp_profile):
    """(goal_mult, assist_mult) ±10% según arquetipo × vulnerabilidad defensiva del rival."""
    bv = opp_profile.get("box_vuln",  0.0)
    wv = opp_profile.get("wide_vuln", 0.0)
    weights = {
        "box_striker":      (bv * 0.14, bv * 0.02),
        "complete_striker": (bv * 0.10, wv * 0.06),
        "wide_fwd":         (wv * 0.05, wv * 0.13),
        "poacher":          (bv * 0.11, bv * 0.01),
        "pressing_fwd":     (bv * 0.05, wv * 0.04),
        "shadow_striker":   (bv * 0.13, bv * 0.04),
        "playmaker":        (wv * 0.03, wv * 0.13),
        "attacking_mid":    (bv * 0.08, bv * 0.07),
        "creative_mid":     (wv * 0.03, wv * 0.09),
        "goalscoring_mid":  (bv * 0.11, bv * 0.02),
        "cdm":              (bv * 0.01, wv * 0.01),
        "box_to_box":       (bv * 0.05, bv * 0.04),
        "overlapping_def":  (bv * 0.01, wv * 0.10),
        "attacking_def":    (bv * 0.03, wv * 0.06),
        "defender":         (0.0, 0.0),
        "other":            (0.0, 0.0),
        # Mediocentro con rol de extremo: proyectar por wide_vuln del rival
        "wide_mid":         (wv * 0.05, wv * 0.12),
    }
    adj = weights.get(player_type, (0.0, 0.0))
    return (
        round(max(0.90, min(1.10, 1.0 + adj[0])), 3),
        round(max(0.90, min(1.10, 1.0 + adj[1])), 3),
    )


_SP_STOP = {"al", "de", "van", "el", "bin", "abu", "le", "la", "di", "da", "du", "den", "der", "dos", "das"}

def _sp_tokens(s):
    import unicodedata
    # Strip diacritics so "Hrustić" matches "Hrustic"
    norm = unicodedata.normalize("NFD", s)
    ascii_s = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return {t for t in ascii_s.lower().replace("-", " ").replace(".", " ").split()
            if len(t) >= 4 and t not in _SP_STOP}


def get_setpiece_role(player_name, team_name, setpieces):
    """
    Devuelve lista de roles set piece del jugador: pk_primary, fk_secondary, etc.
    Matching por apellido (último token del nombre).
    """
    if not setpieces or not player_name:
        return []
    sp = setpieces.get(team_name, {})
    if not sp:
        return []

    name_tokens = _sp_tokens(player_name)
    if not name_tokens:
        return []

    roles = []
    for role_type in ("pk", "fk", "ck"):
        takers = sp.get(role_type, [])
        for idx, taker in enumerate(takers):
            taker_tokens = _sp_tokens(taker)
            if taker_tokens and taker_tokens.issubset(name_tokens):
                if role_type == "ck":
                    # Corners: uno por lado, ambos son titulares
                    roles.append("ck_primary")
                else:
                    rank = "primary" if idx == 0 else "secondary"
                    roles.append(f"{role_type}_{rank}")
                break
    return roles


def apply_setpiece_bonus(xg90, xa90, roles):
    """Suma bonificaciones por rol de set piece (aditivas, no multiplicativas)."""
    xg_add = sum(SP_BONUS.get(r, {}).get("xg", 0) for r in roles)
    xa_add = sum(SP_BONUS.get(r, {}).get("xa", 0) for r in roles)
    return xg90 + xg_add, xa90 + xa_add




def project_player(p_meta, cs, intl_s, form_entry, opp_ts, own_ts, is_home, pos_avgs,
                   opp_name="", lineups=None, event_id=None, setpieces=None, gk_starters=None,
                   lam_opp=None, lam_own=None, def_profiles=None, intl_schedules=None,
                   wc_def_mult=None):
    """
    Proyecta xPts de un jugador para un partido dado.
    p_meta: dict con name, position, national_team, etc.
    cs: club_stats dict (normalizado)
    intl_s: intl_stats dict (normalizado) o None
    form_entry: dict con "form" (form_xg_90, form_xa_90) o None
    """
    pos = _pos_key(p_meta.get("position", ""), player_id=p_meta.get("player_id"))
    if not pos:
        return None

    club_mins  = (cs or {}).get("Minutos Jugados") or 0
    club_games = (cs or {}).get("Partidos Jugados") or 0
    intl_games = (intl_s or {}).get("Partidos Jugados") or 0

    if club_mins < MIN_CLUB_MINS and intl_games < 3:
        return None

    # ── xG/90 y xA/90 blended ──────────────────────────────────────────────
    lq = club_quality(p_meta.get("club_team", ""))
    club_xg90 = get_xg90(cs) * lq
    club_xa90 = get_xa90(cs) * lq
    nat_team = p_meta.get("national_team", "")
    iq = (intl_schedules or {}).get(nat_team, 0.78)
    intl_xg90 = get_xg90(intl_s) * iq if intl_s else None
    intl_xa90 = get_xa90(intl_s) * iq if intl_s else None

    # Delta intl vs club: si el jugador rinde muy distinto en selección, ajustar blend.
    # Si rinde PEOR internacionalmente → dar más peso a intl para penalizarlo.
    # Si rinde MEJOR internacionalmente → dar algo más de peso a intl para beneficiarlo.
    #
    # Para defensas se requiere más muestra (10+ partidos) y el umbral de penalización
    # es más suave: un CB que hace 0.09 xg90 en club pero 0.03 en selección puede
    # simplemente no haber recibido los centros adecuados en solo 6 partidos.
    adj_club_w, adj_intl_w = CLUB_WEIGHT, INTL_WEIGHT
    min_intl_for_penalty = 10 if pos == "D" else 5
    low_ratio  = 0.40 if pos == "D" else 0.60   # DEF: solo penalizar si es realmente muy bajo
    mid_ratio  = 0.55 if pos == "D" else 0.75
    if intl_games >= min_intl_for_penalty and intl_xg90 is not None and club_xg90 > 0.02:
        ratio = intl_xg90 / club_xg90
        if ratio < low_ratio:
            adj_club_w, adj_intl_w = (0.55, 0.45) if pos == "D" else (0.50, 0.50)
        elif ratio < mid_ratio:
            adj_club_w, adj_intl_w = (0.65, 0.35) if pos == "D" else (0.60, 0.40)
        elif ratio > 1.25:
            adj_club_w, adj_intl_w = 0.55, 0.45   # mejor en selección → premiar

    xg90 = blend_xg90(club_xg90, club_games, intl_xg90, intl_games)
    xa90 = blend_xg90(club_xa90, club_games, intl_xa90, intl_games)
    if (adj_club_w != CLUB_WEIGHT) and intl_xg90 is not None:
        xg90 = adj_club_w * club_xg90 + adj_intl_w * intl_xg90
        xa90 = adj_club_w * club_xa90 + adj_intl_w * (intl_xa90 or 0)

    # ── Set piece bonus ───────────────────────────────────────────────────────
    sp_roles = get_setpiece_role(p_meta.get("name", ""), p_meta.get("national_team", ""), setpieces)
    if sp_roles:
        xg90, xa90 = apply_setpiece_bonus(xg90, xa90, sp_roles)

    # ── Blend con forma (nacional, últimos 5) ────────────────────────────────
    has_form = bool(form_entry and form_entry.get("form"))
    if has_form:
        POS_XG_CAP = {"G": 0.20, "D": 0.50, "M": 0.70, "F": 1.10}
        form_xg = min(form_entry["form"]["form_xg_90"], POS_XG_CAP.get(pos, 0.80))
        form_xa = min(form_entry["form"]["form_xa_90"], 0.80)
        # Con pocos PJ de club (<15), la forma WC es más informativa que el historial
        _low_sample_boost = max(0.0, (15 - club_games) / 15 * 0.25) if club_games < 15 else 0.0
        _fw = min(0.75, FORM_WEIGHT + _low_sample_boost)
        _sw = 1.0 - _fw
        xg90 = _sw * xg90 + _fw * form_xg
        xa90 = _sw * xa90 + _fw * form_xa

    # ── Bayesian regression to mean ─────────────────────────────────────────
    effective_games = club_games + intl_games * 0.5   # intl vale menos peso
    xg90_reg, xa90_reg, reg_w = regress_to_mean(xg90, xa90, effective_games, pos, pos_avgs)

    # ── P(titular): blend de minutos/partido club + intl ────────────────────────
    club_mpg = club_mins / max(club_games, 1) if club_games > 0 else 0
    intl_mpg = ((intl_s or {}).get("Minutos Jugados") or 0) / max(intl_games, 1) if intl_games > 0 else None

    # Para xG/xA: blend normal 70/30
    if intl_mpg is not None and intl_games >= 3:
        avg_mins_gm = CLUB_WEIGHT * club_mpg + INTL_WEIGHT * intl_mpg
    else:
        avg_mins_gm = club_mpg

    # Para p_over60: solo minutos internacionales.
    # Sin datos intl → no es titular (0 mins).
    avg_mins_p60 = intl_mpg if intl_mpg is not None else 0

    intl_bias = min(1.0, intl_games / 10)

    # Check lineup data first (overrides minutes-based estimate)
    lineup_status = None
    player_id_str = str(p_meta.get("player_id", ""))
    if lineups and event_id:
        match_lu = lineups.get(str(event_id), {})
        lineup_status = match_lu.get("players", {}).get(player_id_str, {}).get("status")

    player_id_int = int(p_meta.get("player_id", 0))
    if player_id_int in BAJA_OVERRIDES:
        lineup_status = "missing"
    elif player_id_int in SUPLENTE_OVERRIDES:
        lineup_status = "substitute"
    elif player_id_int in ROTACIONAL_OVERRIDES:
        lineup_status = "rotacional"
    elif player_id_int in STARTER_OVERRIDES:
        lineup_status = "starter"

    if lineup_status == "starter":
        p_over60, role, exp_mins = 0.92, "Titular",    85
    elif lineup_status == "substitute":
        p_over60, role, exp_mins = 0.08, "Suplente",   25
    elif lineup_status == "rotacional":
        p_over60, role, exp_mins = 0.45, "Rotacional", 55
    elif lineup_status == "missing":
        p_over60, role, exp_mins = 0.02, "Baja",       0
    else:
        if pos == "G":
            nat_team = p_meta.get("national_team", "")
            is_gk_starter = (gk_starters or {}).get(nat_team) == player_id_int
            # Only use gk_starters fallback if this fixture has NO lineup data at all.
            # If the fixture has lineup entries, missing lineup_status means this GK
            # is not in the squad or is a backup — treat as Suplente.
            fixture_has_lineup = bool((lineups or {}).get(str(event_id), {}).get("players"))
            if is_gk_starter and not fixture_has_lineup:
                p_over60, role, exp_mins = 0.94, "Titular", 90
            else:
                p_over60, role, exp_mins = min(0.08, max(0.02, (avg_mins_gm - 40) / 50)), "Suplente", 5
        else:
            if pos == "D":
                p_over60 = min(0.92, max(0.10, (avg_mins_p60 - 10) / 70))
            elif pos == "M":
                p_over60 = min(0.90, max(0.05, (avg_mins_p60 - 20) / 65))
            else:
                p_over60 = min(0.88, max(0.05, (avg_mins_p60 - 25) / 60))

            if avg_mins_p60 >= 60:
                role, exp_mins = "Titular",    85
            elif avg_mins_p60 >= 35:
                role, exp_mins = "Rotacional", 55
            else:
                role, exp_mins = "Suplente",   25

    p_play   = round(min(0.95, p_over60 + (intl_bias * 0.10 if not lineup_status else 0)), 2)
    mins_fac = exp_mins / 90

    # ── Multiplicadores de matchup ────────────────────────────────────────────
    own_team  = p_meta.get("national_team", "")
    opp_def   = (opp_ts or {}).get("def_score", 50)

    # Host nations: USA/Canada/Mexico play true home games (all their matches in home stadiums)
    if is_home and own_team in HOST_NATIONS:
        home_mult = 1.15
    elif not is_home and opp_name in HOST_NATIONS:
        home_mult = 0.88
    elif is_home:
        home_mult = 1.03
    else:
        home_mult = 0.97

    def_mult  = 1.0 + (50 - opp_def) / 100 * 0.50

    # Player archetype × opponent defensive zone weakness
    _mins_base = max(club_games, 1) * 90
    _shots90  = ((cs or {}).get("Remates Totales") or 0) / _mins_base * 90
    _kp90     = ((cs or {}).get("Pases Clave") or 0)     / _mins_base * 90
    player_type       = classify_player_type(pos, xg90_reg, xa90_reg, _shots90, _kp90)
    if player_id_int in PLAYER_TYPE_OVERRIDES:
        player_type = PLAYER_TYPE_OVERRIDES[player_id_int]
    opp_profile       = (def_profiles or {}).get(opp_name, {})
    g_type_m, a_type_m = get_type_mult(player_type, opp_profile)

    GOAL_POS   = {"G": 0.004, "D": 0.55, "M": 0.70, "F": 0.55}
    ASSIST_POS = {"G": 0.004, "D": 0.11, "M": 0.60, "F": 0.38}

    p_goal   = min(0.45, xg90_reg * def_mult * home_mult * g_type_m * GOAL_POS.get(pos, 0.3)   * mins_fac)
    p_assist = min(0.45, xa90_reg * def_mult * home_mult * a_type_m * ASSIST_POS.get(pos, 0.3) * mins_fac)

    # ── Clean sheet (Poisson) ─────────────────────────────────────────────────
    own_gc_pg  = (own_ts or {}).get("gc_pg")   or LEAGUE_AVG_GC_PG
    own_xgc_pg = (own_ts or {}).get("xgc_pg")  or own_gc_pg
    if lam_opp is not None:
        lam = lam_opp   # lambda del bracket ya incorpora WC form defensivo
    else:
        opp_xgf_pg = (opp_ts or {}).get("gf_pg")   or LEAGUE_AVG_GC_PG
        own_def_pg = own_xgc_pg * 0.60 + own_gc_pg * 0.40
        lam        = (own_def_pg * 0.55 + opp_xgf_pg * 0.45) * (0.85 if is_home else 1.15)
    p_cs       = min(0.65, max(0.03, math.exp(-lam)))

    # ── xSv para arqueros ─────────────────────────────────────────────────────
    xSv_pg = 0.0
    if pos == "G":
        # Blend 60% lam del partido (rival específico, Dixon-Coles) / 40% xgc histórico del equipo.
        # lam ya incorpora calidad del rival y WC form; xgc_pg aporta la señal base de la defensa.
        # Cap a 1.8 goles esperados para evitar que partidos one-sided inflen el xSv.
        lam_capped    = min(lam, 1.8)
        lam_for_saves = lam_capped * 0.60 + own_xgc_pg * 0.40
        xSv_pg = round((lam_for_saves / 0.30) * 0.70, 2)   # shots = goals / 0.30, saves = 70% of shots

    # ── Cards penalty ─────────────────────────────────────────────────────────
    yellows = (cs or {}).get("Amarillas") or 0
    card_pen = (yellows / max(club_games, 1)) * FM["yellow"] if club_games > 0 else 0.0

    # ── Gol definitivo ────────────────────────────────────────────────────────
    own_gf_pg = (own_ts or {}).get("gf_pg", LEAGUE_AVG_GC_PG)
    lam_scored = own_gf_pg * ((opp_ts or {}).get("xgc_pg", LEAGUE_AVG_GC_PG) / max(LEAGUE_AVG_GC_PG, 0.01)) * (1.10 if is_home else 0.90)
    gol_def_pts = p_goal * 0.072 / max(lam_scored, 0.5) * FM["winning_goal"]

    # ── Atajadas ──────────────────────────────────────────────────────────────
    save_pts = (xSv_pg / 3.0) * mins_fac if pos == "G" else 0.0

    # ── Penal atajado (arquero) ───────────────────────────────────────────────
    # ~0.15 penales por partido en selecciones, P(save)≈0.28, vale 5 pts
    pk_saved_pts = 0.15 * 0.28 * 5 * mins_fac if pos == "G" else 0.0

    # ── Corrección gol de penal = 3 pts (no el valor posicional) ─────────────
    # El SP_BONUS pk_primary agrega 0.12 xg/90 que actualmente se valúa a FM["goal"][pos]
    # pero debería valer 3 pts. Aplicamos el diferencial.
    pk_xg_bonus = 0.0
    if "pk_primary" in sp_roles:
        pk_xg = SP_BONUS["pk_primary"]["xg"] * mins_fac
        pk_xg_bonus = pk_xg * (3 - FM["goal"].get(pos, 5))  # negativo para F/M, positivo para G
    elif "pk_secondary" in sp_roles:
        pk_xg = SP_BONUS["pk_secondary"]["xg"] * mins_fac
        pk_xg_bonus = pk_xg * (3 - FM["goal"].get(pos, 5))

    # ── xPts base ─────────────────────────────────────────────────────────────
    xpts = (
        p_goal   * FM["goal"].get(pos, 4)  +
        p_assist * FM["assist"]            +
        p_cs     * FM["cs"].get(pos, 0)    +
        mins_fac * FM["mins"]              +
        card_pen + gol_def_pts + save_pts + pk_saved_pts + pk_xg_bonus
    )

    # Disponibilidad
    xpts = xpts * p_play

    # Consistencia (forma): si hay varianza alta en forma, pequeño descuento
    form_n = (form_entry or {}).get("form", {}).get("n", 0) if has_form else 0
    if has_form and form_n >= 3:
        form_matches = (form_entry or {}).get("matches", [])
        outputs = [(m["xg"] + m["xa"]) / m["mins"] * 90
                   for m in form_matches if (m.get("mins") or 0) >= 20]
        if len(outputs) >= 2:
            mean = sum(outputs) / len(outputs)
            if mean > 0.02:
                var  = sum((x - mean)**2 for x in outputs) / len(outputs)
                cv   = (var ** 0.5) / mean
                consistency = max(0, min(100, round(100 - cv * 50)))
                xpts *= (0.94 + 0.12 * consistency / 100)

    xpts = round(xpts, 2)

    # Cap score (sin BPR)
    CAP_POS_MULT = {"G": 0.70, "D": 0.88, "M": 1.00, "F": 1.08}
    cap_score = round(xpts * CAP_POS_MULT.get(pos, 1.0), 2)

    return {
        "p_goal":        round(p_goal   * 100, 1),
        "p_assist":      round(p_assist * 100, 1),
        "p_cs":          round(p_cs     * 100, 1),
        "p_play":        p_play,
        "xg90":          round(xg90,     3),
        "xa90":          round(xa90,     3),
        "xg90_reg":      round(xg90_reg, 3),
        "xa90_reg":      round(xa90_reg, 3),
        "has_form":      has_form,
        "role":          role,
        "lineup_status": lineup_status,
        "player_type":   player_type,
        "sp_roles":      sp_roles,
        "mins_fac":      round(mins_fac, 2),
        "xpts":          xpts,
        "cap_score":     cap_score,
        "xSv_pg":        xSv_pg,
        "fdr_opp":       (opp_ts or {}).get("fdr", 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", type=int, default=None,
                        help="Filtrar solo fecha N de grupos (1, 2 o 3)")
    args = parser.parse_args()

    players_raw, team_stats, form_data, fixtures, lineups, setpieces, predictions, coaches, match_analytics, wc_results = load_data(args.fecha)

    # Mapa fixture: team_name → [(opp_name, is_home, event_id, round_num)]
    from collections import defaultdict
    fixture_map = defaultdict(list)
    for fx in fixtures:
        h = fx["home_name"]
        a = fx["away_name"]
        if h and a:
            fixture_map[h].append((a, True,  fx["event_id"], fx.get("round_num")))
            fixture_map[a].append((h, False, fx["event_id"], fx.get("round_num")))

    # Para octavos (round_num=4) usar el lineup de F3 del mismo equipo como base.
    # Grimaldo fix: sin este fallback, jugadores con buen historial pero sin minutos en el
    # Mundial aparecen como titulares porque el evento ficticio no tiene datos de lineup.
    team_f3_eid = {}  # team_name → event_id de su partido F3
    for fx in fixtures:
        if fx.get("round_num") == 3:
            if fx.get("home_name"): team_f3_eid[fx["home_name"]] = fx["event_id"]
            if fx.get("away_name"): team_f3_eid[fx["away_name"]] = fx["event_id"]

    # Para cuartos (round_num=5) usar el lineup de Octavos (round_num=4) del mismo equipo.
    team_ko_eid = {}  # team_name → event_id de su partido de Octavos
    for fx in fixtures:
        if fx.get("round_num") == 4:
            if fx.get("home_name"): team_ko_eid[fx["home_name"]] = fx["event_id"]
            if fx.get("away_name"): team_ko_eid[fx["away_name"]] = fx["event_id"]

    # Patrón de sustitución temprana: jugador con sub_in en F2 Y F3 consecutivamente
    # Minutos reales del Mundial F1+F2+F3 para ajustar exp_mins en Octavos.
    # F1 fue re-scrapeado con minutesPlayed correcto (bug de 1089min resuelto).
    # Cap <200 como seguridad extra.
    # F3 incluido pero con peso menor: muchos equipos rotaron al tener el grupo resuelto.
    # Pesos: F2=2.0, F1=1.5, F3=0.5 → F2 pesa más (partido más serio y reciente).
    WC_ROUND_WEIGHTS = {1: 1.5, 2: 2.0, 3: 0.5, 4: 3.0}   # round 4 = Octavos (peso máximo)
    wc_mins_by_round = {}   # pid_str → {round_num: mins}
    for eid_str, md in wc_results.get("matches", {}).items():
        rnd = md.get("round_num")
        if rnd not in (1, 2, 3, 4):
            continue
        for pid_str, ps in md.get("player_stats", {}).items():
            mins = ps.get("mins") or 0
            if 0 < mins < 200:   # excluye 0 (no jugó) y bugs residuales
                wc_mins_by_round.setdefault(pid_str, {})[rnd] = mins

    # Proyección de minutos y status para Octavos.
    #
    # Lógica de titularidad (avg F1+F2 cuenta 0 si no jugó, nunca nulo):
    #   avg_f1f2 >= 60 → titular claro
    #   avg_f1f2 >= 30 → revisar F3: si fue titular en F3 → titular; si no → rotacional
    #   avg_f1f2 <  30 → gate → Suplente directo
    #
    # Minutos proyectados: promedio ponderado solo de fechas donde fue titular (≥60min),
    # no mezclar partidos como sub (evita que un descanso en F3 baje la proyección).
    WC_STARTER_THRESHOLD = 60

    wc_starter_f1   = set()   # jugó ≥60min en F1
    wc_starter_f2   = set()   # jugó ≥60min en F2
    wc_starter_f3   = set()   # jugó ≥60min en F3
    wc_avg_f1f2     = {}      # pid → promedio (F1+F2)/2 usando 0 para partidos no jugados
    wc_starter_mins = {}      # pid → promedio ponderado de fechas como titular

    # Para calcular avg_f1f2 necesitamos saber qué equipos jugaron F1 y F2 ya que un
    # jugador podría simplemente no tener datos porque el match no fue scrapeado aún.
    teams_with_f1 = {md["home"] for md in wc_results["matches"].values() if md.get("round_num") == 1} | \
                    {md["away"] for md in wc_results["matches"].values() if md.get("round_num") == 1}
    teams_with_f2 = {md["home"] for md in wc_results["matches"].values() if md.get("round_num") == 2} | \
                    {md["away"] for md in wc_results["matches"].values() if md.get("round_num") == 2}

    # pid → equipo (para saber si su selección jugó F1/F2)
    pid_to_team: dict[str, str] = {}
    for md in wc_results["matches"].values():
        for pid_str, ps in md.get("player_stats", {}).items():
            if pid_str not in pid_to_team:
                tid = ps.get("team_id")
                home_id = md.get("home_id")
                pid_to_team[pid_str] = md["home"] if tid == home_id else md["away"]

    for pid_str, rnd_mins in wc_mins_by_round.items():
        m1 = rnd_mins.get(1, 0)
        m2 = rnd_mins.get(2, 0)
        m3 = rnd_mins.get(3, 0)

        if m1 >= WC_STARTER_THRESHOLD: wc_starter_f1.add(pid_str)
        if m2 >= WC_STARTER_THRESHOLD: wc_starter_f2.add(pid_str)
        if m3 >= WC_STARTER_THRESHOLD: wc_starter_f3.add(pid_str)

        # Promedio F1+F2 con 0 para partidos no jugados (nunca nulo)
        team = pid_to_team.get(pid_str, "")
        games = 0
        if team in teams_with_f1: games += 1
        if team in teams_with_f2: games += 1
        if games > 0:
            wc_avg_f1f2[pid_str] = (m1 + m2) / games

        # Minutos proyectados: solo de fechas donde fue titular
        total_w = total_wm = 0.0
        for rnd, mins in rnd_mins.items():
            if mins < WC_STARTER_THRESHOLD:
                continue
            w = WC_ROUND_WEIGHTS.get(rnd, 1.0)
            total_wm += mins * w
            total_w  += w
        if total_w > 0:
            wc_starter_mins[pid_str] = total_wm / total_w

    # wc_avg_mins alias para compatibilidad con el bloque de ajuste de minutos downstream
    wc_avg_mins = wc_starter_mins

    # Minutos de cada jugador en Octavos (round_num=4) — usado como señal primaria para Cuartos gate
    wc_ko_mins = {pid: rnd_mins[4] for pid, rnd_mins in wc_mins_by_round.items() if 4 in rnd_mins}

    # ── WC Defensive Form: ajuste lambda rival por GC ponderados en F1/F2/F3 ──
    # F3 con rotaciones pesa menos (WC_ROUND_WEIGHTS). Reduce lam_opp si el equipo
    # defendió mejor de lo esperado históricamente.
    WC_DEF_WEIGHT    = 0.45   # cuánto pesa el WC vs el DC histórico
    WC_DEF_CAP       = (0.60, 1.35)
    LEAGUE_AVG_GC_PG = 1.15

    _wc_gc_w: dict[str, float] = {}   # team → weighted goals conceded
    _wc_gc_n: dict[str, float] = {}   # team → sum of round weights

    for _eid_str, _md in wc_results.get("matches", {}).items():
        _rnd = _md.get("round_num")
        if _rnd not in (1, 2, 3, 4): continue
        _sh = _md.get("score_home"); _sa = _md.get("score_away")
        if _sh is None or _sa is None: continue
        _rnd_w = WC_ROUND_WEIGHTS.get(_rnd, 1.0)
        for _tname, _is_h in [(_md["home"], True), (_md["away"], False)]:
            _gc = _sa if _is_h else _sh
            _wc_gc_w[_tname] = _wc_gc_w.get(_tname, 0.0) + _gc * _rnd_w
            _wc_gc_n[_tname] = _wc_gc_n.get(_tname, 0.0) + _rnd_w

    wc_def_mult: dict[str, float] = {}
    for _tname in _wc_gc_w:
        _gc_pg = _wc_gc_w[_tname] / _wc_gc_n[_tname]
        # Comparar vs el histórico propio del equipo, no vs promedio de liga genérico.
        # Así si un equipo concede MÁS que su histórico → mult > 1 → p_cs baja (correcto).
        _hist_gc = (team_stats.get(_tname) or {}).get("gc_pg") or LEAGUE_AVG_GC_PG
        _ratio = _gc_pg / _hist_gc                   # < 1 = mejor que su propio histórico
        _mult  = (1 - WC_DEF_WEIGHT) + WC_DEF_WEIGHT * _ratio
        wc_def_mult[_tname] = max(WC_DEF_CAP[0], min(WC_DEF_CAP[1], _mult))

    # Patrón F2+F3: no se usa para sub_in detection — eliminado porque genera
    # demasiados falsos positivos (titulares que salen antes de 60min en ambos juegos).
    # El ajuste de minutos via wc_avg_mins es suficiente.
    wc_early_sub_pattern: set = set()

    pos_avgs = compute_positional_averages(players_raw)

    # Perfiles defensivos por selección (box/wide vulnerability)
    def_profiles = team_defensive_profiles(players_raw)
    print(f"[def_profiles] {len(def_profiles)} selecciones con perfil defensivo")

    # Calidad de rivales internacionales basada en ranking FIFA real de cada rival
    intl_schedules = compute_intl_schedules(match_analytics, team_stats)
    for t, q in sorted(intl_schedules.items(), key=lambda x: x[1]):
        print(f"  intl_q {t:<25} {q:.3f}")

    # FDR desde beta del modelo Dixon-Coles (ya ajustado por calidad del rival).
    # Beta bajo = buena defensa = difícil de atacar = FDR 1 (rojo).
    # Fallback a def_score percentil solo si el equipo no está en el modelo.
    pred_params = predictions.get("team_params", {})
    betas = sorted(p["beta"] for p in pred_params.values()) if pred_params else []
    nb = len(betas)
    def _beta_pct(p): return betas[int(nb * p / 100)] if nb else 0
    bp20, bp40, bp60, bp80 = _beta_pct(20), _beta_pct(40), _beta_pct(60), _beta_pct(80)

    def_scores = sorted(v.get("def_score", 50) for v in team_stats.values())
    nd = len(def_scores)
    def _ds_pct(p): return def_scores[int(nd * p / 100)]
    dp20, dp40, dp60, dp80 = _ds_pct(20), _ds_pct(40), _ds_pct(60), _ds_pct(80)

    all_team_names = set(team_stats.keys()) | set(pred_params.keys())
    for team_name in all_team_names:
        v = team_stats.setdefault(team_name, {})
        beta = pred_params.get(team_name, {}).get("beta")
        if beta is not None and nb > 0:
            # Menor beta → mejor defensa → más difícil atacar → FDR más bajo
            v["fdr"] = (1 if beta <= bp20 else 2 if beta <= bp40 else 3 if beta <= bp60 else 4 if beta <= bp80 else 5)
        else:
            ds = v.get("def_score", 50)
            v["fdr"] = (1 if ds >= dp80 else 2 if ds >= dp60 else 3 if ds >= dp40 else 4 if ds >= dp20 else 5)

    # Pre-compute starter GK per national team (highest avg_mins_gm among GKs)
    # Only consider players in the official WC squad to avoid picking retired/non-squad GKs
    with open(BASE_DIR / "wc2026_squads.json", encoding="utf-8") as _sqf:
        _squads_raw = json.load(_sqf)
    _wc_squad_pids = {int(p["id"]) for td in _squads_raw.values() for p in td.get("players", []) if p.get("id")}

    from collections import defaultdict as _dd
    _gk_by_team = _dd(list)
    for _pid, _pm in players_raw.items():
        if _pos_key(_pm.get("position", "")) != "G":
            continue
        if int(_pid) not in _wc_squad_pids:
            continue  # skip GKs not in any WC squad
        _team = _pm.get("national_team", "")
        if not _team:
            continue
        _cs = _pm.get("club_stats") or {}
        _is = _pm.get("intl_stats") or {}
        _itot = _is.get("Minutos Jugados") or 0
        _ig   = _is.get("Partidos Jugados") or 0
        _cm   = (_cs.get("Minutos Jugados") or 0)
        # Si tiene al menos 2 partidos intl, el total de minutos intl define el titular
        # Si no, usar minutos de club como fallback
        _avg = (_itot * 1000) + _cm if _ig >= 2 else _cm
        _gk_by_team[_team].append((_avg, int(_pid)))
    gk_starters = {t: sorted(gks, reverse=True)[0][1] for t, gks in _gk_by_team.items()}
    gk_starters.update(GK_STARTER_OVERRIDES)

    # Suspensiones y lesiones desde resultados WC (roja directa o doble amarilla)
    # Se agregan como "missing" en el lineup del siguiente partido del equipo
    wc_team_profiles = wc_results.get("team_profiles", {})
    _wc_suspended = set()
    for eid_str, md in wc_results.get("matches", {}).items():
        round_num_played = md.get("round_num", 0)
        home_id = md.get("home_id")
        away_id = md.get("away_id")
        for miss in md.get("incidents", {}).get("missing_next", []):
            pid = miss.get("player_id")
            tid = miss.get("team_id")
            if not pid or not tid:
                continue
            # Buscar el partido siguiente de este equipo en los fixtures cargados
            for fx in sorted(fixtures, key=lambda x: x.get("round_num", 99)):
                if fx.get("round_num", 0) <= round_num_played:
                    continue
                if fx.get("home_id") == tid or fx.get("away_id") == tid:
                    next_eid = str(fx["event_id"])
                    if next_eid not in lineups:
                        lineups[next_eid] = {"players": {}, "confirmed": False}
                    lineups[next_eid].setdefault("players", {})[str(pid)] = {
                        "status": "missing",
                        "reason": miss.get("reason", "suspension"),
                        "from_wc_result": True,
                    }
                    _wc_suspended.add(pid)
                    break

    if _wc_suspended:
        print(f"[wc_results] {len(_wc_suspended)} jugadores suspendidos/bajas para siguiente fecha")

    print(f"[gk_starters] {len(gk_starters)} titulares detectados")

    # Índice de lambdas del modelo por event_id → {home_team: lam_h, away_team: lam_a}
    lambda_index = {}
    for fx in predictions.get("fixtures", []):
        eid = fx.get("event_id")
        if eid:
            lambda_index[eid] = {
                fx["home"]: fx["lambda_away"],  # lambda que enfrenta el GK del equipo home
                fx["away"]: fx["lambda_home"],  # lambda que enfrenta el GK del equipo away
            }

    # Cargar fixtures de Octavos de Final (wc2026_knockout.json)
    _knockout_path = BASE_DIR / "wc2026_knockout.json"
    if _knockout_path.exists():
        _ko = json.load(open(_knockout_path, encoding="utf-8"))
        _ko_added = 0
        for fx in _ko.get("fixtures", []):
            h = fx.get("home_name", "TBD")
            a = fx.get("away_name", "TBD")
            eid = fx.get("event_id")
            lam_h = fx.get("lambda_home")
            lam_a = fx.get("lambda_away")
            if h == "TBD" or a == "TBD" or not eid:
                continue
            fixture_map[h].append((a, True,  eid, 4))
            fixture_map[a].append((h, False, eid, 4))
            if lam_h and lam_a:
                lambda_index[eid] = {h: lam_a, a: lam_h}
                # Calcular ev_home_dt y score_dist para Panel DT de Octavos
                _ev_h = _ev_a = 0.0
                _score_dist: dict = {}
                _MAX_G = 9
                for _i in range(_MAX_G):
                    for _j in range(_MAX_G):
                        _p = (math.exp(-lam_h)*lam_h**_i/math.factorial(_i) *
                              math.exp(-lam_a)*lam_a**_j/math.factorial(_j))
                        _ev_h += _p * (_i - _j)
                        _ev_a += _p * (_j - _i)
                        _score_dist[f"{_i}-{_j}"] = round(_p, 4)
                # Agregar a predictions["fixtures"] con round=4 para Panel DT
                predictions.setdefault("fixtures", []).append({
                    "event_id":    eid,
                    "round":       4,
                    "group":       "KO",
                    "home":        h,
                    "away":        a,
                    "lambda_home": lam_h,
                    "lambda_away": lam_a,
                    "p_home_win":  fx.get("p_home_win"),
                    "p_draw":      fx.get("p_draw"),
                    "p_away_win":  fx.get("p_away_win"),
                    "ev_home_dt":  round(_ev_h, 3),
                    "ev_away_dt":  round(_ev_a, 3),
                    "score_dist":  _score_dist,
                    "home_form":   None,
                    "away_form":   None,
                })
            _ko_added += 1
        print(f"[knockout] {_ko_added} matchups de octavos cargados en fixture_map")

        # ── Cuartos de Final (round_num=5) ────────────────────────────────────
        _cuartos_added = 0
        for fx in _ko.get("cuartos", []):
            h = fx.get("home_name", "TBD")
            a = fx.get("away_name", "TBD")
            eid  = fx.get("event_id")
            lam_h = fx.get("lambda_home")
            lam_a = fx.get("lambda_away")
            if h == "TBD" or a == "TBD" or not eid:
                continue
            fixture_map[h].append((a, True,  eid, 5))
            fixture_map[a].append((h, False, eid, 5))
            if lam_h and lam_a:
                lambda_index[eid] = {h: lam_a, a: lam_h}
                _ev_h = _ev_a = 0.0
                _score_dist_c: dict = {}
                for _i in range(9):
                    for _j in range(9):
                        _p = (math.exp(-lam_h)*lam_h**_i/math.factorial(_i) *
                              math.exp(-lam_a)*lam_a**_j/math.factorial(_j))
                        _ev_h += _p * (_i - _j)
                        _ev_a += _p * (_j - _i)
                        _score_dist_c[f"{_i}-{_j}"] = round(_p, 4)
                predictions.setdefault("fixtures", []).append({
                    "event_id":    eid,
                    "round":       5,
                    "group":       "KO",
                    "home":        h,
                    "away":        a,
                    "lambda_home": lam_h,
                    "lambda_away": lam_a,
                    "p_home_win":  fx.get("p_home_win"),
                    "p_draw":      fx.get("p_draw"),
                    "p_away_win":  fx.get("p_away_win"),
                    "ev_home_dt":  round(_ev_h, 3),
                    "ev_away_dt":  round(_ev_a, 3),
                    "score_dist":  _score_dist_c,
                    "home_form":   None,
                    "away_form":   None,
                })
            _cuartos_added += 1
        print(f"[knockout] {_cuartos_added} matchups de cuartos cargados en fixture_map")

    # ── BPR: rating promedio ponderado por calidad del rival ─────────────────
    # Lookup event_id → opponent_fifa_score usando nombre del rival (como compute_intl_schedules)
    _fifa_all: dict = {}
    _fifa_all.update(_FIFA_RANK_EXT)
    _fifa_all.update({n: d["fifa_rank_score"] for n, d in team_stats.items()})

    def _lookup_fifa(opp_name: str):
        if not opp_name:
            return 30
        if opp_name in _fifa_all:
            return _fifa_all[opp_name]
        low = opp_name.lower()
        for k, v in _fifa_all.items():
            if k and (k.lower() in low or low in k.lower()):
                return v
        return 30  # default: rival débil desconocido

    _event_opp_q: dict = {}
    for _team, _tdata in match_analytics.items():
        for _m in _tdata.get("matches", []):
            _eid = _m.get("event_id")
            _opp_name = _m.get("opponent", "")
            if _eid:
                _event_opp_q[_eid] = _lookup_fifa(_opp_name)

    WC_BPR_MULT = 1.0  # sin multiplicador extra: el peso viene solo de la recencia en el form

    avg_rating = {}
    has_real_rating = set()
    for pid, fd in form_data.items():
        if fd and fd.get("matches"):
            w_sum, w_total = 0.0, 0.0
            for m in fd["matches"]:
                r = m.get("rating")
                if r is None:
                    continue
                opp_q    = _event_opp_q.get(m.get("event_id"), 30)
                wc_bonus = WC_BPR_MULT if m.get("is_wc") else 1.0
                w = (opp_q ** 1.5) * wc_bonus
                w_sum   += r * w
                w_total += w
            if w_total > 0:
                avg_rating[pid] = w_sum / w_total
                has_real_rating.add(pid)

    # Pool de jugadores con rating real por partido
    from collections import defaultdict as _dd2
    fixture_player_pool = _dd2(list)
    for pid_str2, p_meta2 in players_raw.items():
        team2 = p_meta2.get("national_team", "")
        if pid_str2 in avg_rating:
            for _, _, eid2, _ in fixture_map.get(team2, []):
                fixture_player_pool[eid2].append(pid_str2)

    # Pesos softmax por partido (Plackett-Luce)
    _bpr_weights = {}
    for eid, pids in fixture_player_pool.items():
        ws = {p: math.exp(avg_rating[p] / BPR_SIGMA) for p in pids}
        _bpr_weights[eid] = (ws, sum(ws.values()))

    def _bpr_ev(pid_str, eid):
        """EV de puntos BPR (3/2/1 top 3) con modelo Plackett-Luce."""
        if eid not in _bpr_weights or pid_str not in avg_rating:
            return 0.0
        ws, W = _bpr_weights[eid]
        if pid_str not in ws:
            return 0.0
        w_i = ws[pid_str]
        pids = list(ws.keys())
        # P(rank 1)
        p1 = w_i / W
        # P(rank 2) exacto Plackett-Luce
        p2 = sum((ws[j] / W) * (w_i / (W - ws[j])) for j in pids if j != pid_str)
        # P(rank 3)
        p3 = 0.0
        for j in pids:
            if j == pid_str: continue
            wj, Wj = ws[j], W - ws[j]
            p3 += sum((ws[j] / W) * (ws[k] / Wj) * (w_i / (Wj - ws[k]))
                      for k in pids if k != pid_str and k != j)
        return BPR_POINTS[0] * p1 + BPR_POINTS[1] * p2 + BPR_POINTS[2] * p3

    print(f"[bpr] {len(avg_rating)} jugadores con rating promedio real")


    # Solo proyectar jugadores que están en el squad oficial actual
    with open(BASE_DIR / "wc2026_squads.json", encoding="utf-8") as f:
        _squads_now = json.load(f)
    official_squad_ids = {str(p["id"]) for td in _squads_now.values() for p in td.get("players", [])}

    player_list = []
    for pid_str, p_meta in players_raw.items():
        if pid_str not in official_squad_ids:
            continue  # jugador ya no está en el squad oficial
        p_meta.setdefault("player_id", int(pid_str))
        team = p_meta.get("national_team", "")
        if team not in fixture_map:
            continue

        cs     = p_meta.get("club_stats")
        intl_s = p_meta.get("intl_stats")
        fe     = form_data.get(pid_str, {})

        for opp_name, is_home, event_id, round_num in fixture_map[team]:
            own_ts = team_stats.get(team)
            opp_ts = team_stats.get(opp_name)
            lam_idx = lambda_index.get(event_id, {})
            lam_opp = lam_idx.get(team)   # lambda del rival atacando → define p_cs del GK local
            lam_own = lam_idx.get(opp_name)

            # Para octavos, usar el event_id de F3 del mismo equipo para el lookup de lineup.
            # Los event_ids 9000000X no existen en lineups.json → sin este fallback cualquier
            # jugador con buen historial aparece como "Titular" aunque no haya jugado en el WC.
            lineup_event_id = event_id
            if round_num == 4:
                lineup_event_id = team_f3_eid.get(team, event_id)
            elif round_num == 5:
                lineup_event_id = team_ko_eid.get(team, team_f3_eid.get(team, event_id))

            # Patrón sub_in F2+F3: baja a rotacional para Octavos.
            # No aplica si hay override manual ni si el jugador no fue sub en ambas fechas.
            _pid_str  = pid_str          # string ID del jugador actual (clave en lineups/wc_avg_mins)
            _pid_int  = int(pid_str)     # int para STARTER/ROTACIONAL/BAJA_OVERRIDES

            # Para Octavos: determinar lineup status desde historial WC real.
            # avg_f1f2 = (mins_F1 + mins_F2) / 2  usando 0 si no jugó (nunca nulo)
            #   avg >= 60 → titular claro → forzar starter
            #   avg >= 30 → desempatar con F3: si fue titular en F3 → starter
            #   avg <  30 → gate lo baja a Suplente (ver bloque post-wc_avg_mins)
            if round_num == 4 and _pid_int not in STARTER_OVERRIDES and _pid_int not in ROTACIONAL_OVERRIDES:
                _avg_f1f2 = wc_avg_f1f2.get(_pid_str, 0.0)
                _in_f3    = _pid_str in wc_starter_f3
                _force_starter = False
                if _avg_f1f2 >= 80:
                    _force_starter = True          # 80+ min avg → titular claro, sin necesitar F3
                elif _avg_f1f2 >= 30:
                    _force_starter = _in_f3        # 30-80 min avg → F3 desempata
                # avg < 30 → no forzar, gate lo filtra
                if _force_starter:
                    _lu = lineups.setdefault(str(lineup_event_id), {}).setdefault("players", {})
                    _cur = _lu.get(_pid_str, {})
                    if _cur.get("status") not in ("starter",):
                        _lu[_pid_str] = {**_cur, "status": "starter"}

            # Para Cuartos (round_num=5): solo minutos de Octavos.
            # ≥60 min → titular; gate downstream maneja el resto.
            if round_num == 5 and _pid_int not in STARTER_OVERRIDES and _pid_int not in ROTACIONAL_OVERRIDES:
                _ko_mins = wc_ko_mins.get(_pid_str, 0)
                if _ko_mins >= 60:
                    _lu = lineups.setdefault(str(lineup_event_id), {}).setdefault("players", {})
                    _cur = _lu.get(_pid_str, {})
                    if _cur.get("status") not in ("starter",):
                        _lu[_pid_str] = {**_cur, "status": "starter"}

            proj = project_player(p_meta, cs, intl_s, fe, opp_ts, own_ts, is_home, pos_avgs,
                                  opp_name=opp_name, lineups=lineups, event_id=lineup_event_id,
                                  setpieces=setpieces, gk_starters=gk_starters,
                                  lam_opp=lam_opp, lam_own=lam_own,
                                  def_profiles=def_profiles,
                                  intl_schedules=intl_schedules,
                                  wc_def_mult=wc_def_mult)
            if proj is None:
                continue

            # 1) Ajuste de minutos reales del Mundial para KO rounds.
            # Octavos (round_num=4): usa promedio ponderado de F1+F2+F3.
            # Cuartos (round_num=5): usa minutos reales jugados en Octavos.
            if round_num == 4 and _pid_str in wc_avg_mins:
                avg_m        = wc_avg_mins[_pid_str]
                old_mf       = proj.get("mins_fac", 1.0)
                old_pp       = proj.get("p_play", 0.9)
                new_mf       = round(min(1.0, avg_m / 90), 3)
                new_p_over60 = round(min(0.95, max(0.05, avg_m / 75)), 2)
                if old_mf > 0 and old_pp > 0:
                    scale        = (new_mf / old_mf) * (new_p_over60 / old_pp)
                    proj["xpts"] = round(proj["xpts"] * scale, 2)
                proj["exp_mins"] = round(avg_m)
                proj["mins_fac"] = new_mf
                proj["p_over60"] = new_p_over60
                proj["p_play"]   = new_p_over60
                if proj.get("lineup_status") not in ("starter", "rotacional", "substitute", "missing"):
                    if new_p_over60 >= 0.80:
                        proj["role"] = "Titular"
                    elif new_p_over60 >= 0.50:
                        proj["role"] = "Rotacional"
                    else:
                        proj["role"] = "Suplente"

            if round_num == 5 and _pid_str in wc_ko_mins:
                ko_m         = wc_ko_mins[_pid_str]
                old_mf       = proj.get("mins_fac", 1.0)
                old_pp       = proj.get("p_play", 0.9)
                new_mf       = round(min(1.0, ko_m / 90), 3)
                new_p_over60 = round(min(0.95, max(0.05, ko_m / 75)), 2)
                if old_mf > 0 and old_pp > 0:
                    scale        = (new_mf / old_mf) * (new_p_over60 / old_pp)
                    proj["xpts"] = round(proj["xpts"] * scale, 2)
                proj["exp_mins"] = round(ko_m)
                proj["mins_fac"] = new_mf
                proj["p_over60"] = new_p_over60
                proj["p_play"]   = new_p_over60
                if proj.get("lineup_status") not in ("starter", "rotacional", "substitute", "missing"):
                    if new_p_over60 >= 0.80:
                        proj["role"] = "Titular"
                    elif new_p_over60 >= 0.50:
                        proj["role"] = "Rotacional"
                    else:
                        proj["role"] = "Suplente"

            # 2) Gate — aplicar DESPUÉS del ajuste de minutos.
            # avg_f1f2 < 30 → Suplente directo
            # avg_f1f2 >= 30 pero no forzado a starter (ambiguo sin F3) → Rotacional cap
            # No aplica a jugadores con override.
            if round_num == 4 and _pid_int not in STARTER_OVERRIDES and _pid_int not in BAJA_OVERRIDES:
                _avg_f1f2 = wc_avg_f1f2.get(_pid_str, 0.0)
                _in_f3    = _pid_str in wc_starter_f3
                if _avg_f1f2 < 30:
                    # Directamente Suplente: no jugó en el Mundial o solo un par de minutos
                    old_pp = proj.get("p_play", 0.9)
                    new_pp = 0.20
                    if old_pp > new_pp:
                        proj["xpts"] = round(proj["xpts"] * (new_pp / old_pp), 2)
                    proj["p_play"]   = min(old_pp, new_pp)
                    proj["p_over60"] = min(old_pp, new_pp)
                    proj["exp_mins"] = 18
                    proj["mins_fac"] = round(18 / 90, 3)
                    proj["role"]     = "Suplente"
                elif _avg_f1f2 < 80 and not _in_f3:
                    # Jugó algo en F1/F2 pero no es titular claro y no confirma F3
                    old_pp = proj.get("p_play", 0.9)
                    new_pp = 0.45
                    if old_pp > new_pp:
                        proj["xpts"] = round(proj["xpts"] * (new_pp / old_pp), 2)
                    proj["p_play"]   = min(old_pp, new_pp)
                    proj["p_over60"] = min(old_pp, new_pp)
                    proj["exp_mins"] = min(proj.get("exp_mins", 40), 40)
                    proj["mins_fac"] = round(proj["exp_mins"] / 90, 3)
                    proj["role"]     = "Rotacional"

            # Gate para Cuartos (round_num=5): basado exclusivamente en minutos de Octavos.
            # ≤30 min (o 0) → Suplente; 31-59 min → Rotacional ajustado; ≥60 → libre (titular).
            if round_num == 5 and _pid_int not in STARTER_OVERRIDES and _pid_int not in BAJA_OVERRIDES:
                _ko_mins = wc_ko_mins.get(_pid_str, 0)
                if _ko_mins <= 30:
                    # No jugó Octavos o solo minutos testimoniales → Suplente
                    old_pp = proj.get("p_play", 0.9)
                    new_pp = 0.20
                    if old_pp > new_pp:
                        proj["xpts"] = round(proj["xpts"] * (new_pp / old_pp), 2)
                    proj["p_play"]   = min(old_pp, new_pp)
                    proj["p_over60"] = min(old_pp, new_pp)
                    proj["exp_mins"] = round(_ko_mins * 0.6) if _ko_mins > 0 else 15
                    proj["mins_fac"] = round(proj["exp_mins"] / 90, 3)
                    proj["role"]     = "Suplente"
                elif _ko_mins < 60:
                    # Jugó entre 31 y 59 min → Rotacional, exp_mins = 60% de lo jugado
                    old_pp = proj.get("p_play", 0.9)
                    new_pp = round(min(0.55, _ko_mins / 90), 2)
                    if old_pp > new_pp:
                        proj["xpts"] = round(proj["xpts"] * (new_pp / old_pp), 2)
                    proj["p_play"]   = min(old_pp, new_pp)
                    proj["p_over60"] = min(old_pp, new_pp)
                    proj["exp_mins"] = round(_ko_mins * 0.75)
                    proj["mins_fac"] = round(proj["exp_mins"] / 90, 3)
                    proj["role"]     = "Rotacional"
                # ≥60 min → no tocar, la proyección normal es válida

            xbpr = min(round(_bpr_ev(pid_str, event_id), 3), 0.80)  # cap: un partido no puede garantizar BPR

            # Ajuste de xbpr por dificultad del partido según posición.
            # El BPR de un GK o DEF está correlacionado con si el equipo defiende bien
            # → p_cs es un buen proxy de la chance de tener un partido de alto rating.
            # GK: ajuste fuerte (CS es casi el único driver del BPR del arquero)
            # DEF: ajuste suave (goles/asistencias también aportan, cap más alto)
            # MID/FWD: sin ajuste (su BPR no depende tanto de la defensa del equipo)
            pos_key = _pos_key(p_meta.get("position", ""), player_id=p_meta.get("player_id"))
            p_cs_match = proj.get("p_cs", 50.0) / 100.0   # p_cs ya está en %
            if pos_key == "G":
                # max(0.35, p_cs/0.65): a p_cs=65% → factor=1.0; p_cs=28% → factor=0.44
                bpr_match_adj = max(0.35, p_cs_match / 0.65)
                xbpr = round(xbpr * bpr_match_adj, 3)
            elif pos_key == "D":
                # Ajuste más suave: 50% ponderado por p_cs, 50% fijo
                # max(0.60, 0.5 + p_cs/0.65 * 0.5): p_cs=65%→1.0; p_cs=28%→0.72; p_cs=10%→0.60
                bpr_match_adj = max(0.60, 0.5 + (p_cs_match / 0.65) * 0.5)
                xbpr = round(xbpr * bpr_match_adj, 3)

            proj["xpts"] = round(proj["xpts"] + xbpr, 3)

            player_list.append({
                "player_id":  int(pid_str),
                "name":       p_meta.get("name", "?"),
                "team":       team,
                "opp":        opp_name,
                "group":      p_meta.get("group", "?"),
                "is_home":    is_home,
                "pos":        _pos_key(p_meta.get("position", ""), player_id=p_meta.get("player_id")),
                "jersey":     p_meta.get("jersey"),
                "club":       p_meta.get("club_team", ""),
                "event_id":   event_id,
                "round_num":  round_num,
                "club_games": (cs or {}).get("Partidos Jugados") or 0,
                "club_mins":  (cs or {}).get("Minutos Jugados") or 0,
                "intl_games": (intl_s or {}).get("Partidos Jugados") or 0,
                "goals_club": (cs or {}).get("Goles") or 0,
                "ast_club":   (cs or {}).get("Asistencias") or 0,
                "amarillas":  (cs or {}).get("Amarillas") or 0,
                "xbpr":       xbpr,
                **proj,
            })

    player_list.sort(key=lambda x: x["xpts"], reverse=True)
    print(f"\nJugadores proyectados: {len(player_list)}")

    # FDR table
    fdr_table = sorted(
        [{"team": t, **v} for t, v in team_stats.items()],
        key=lambda x: x.get("def_score", 50),
        reverse=True,
    )

    # Compact fecha 1 data for HTML display
    wc_fecha1 = []
    for eid_str, md in wc_results.get("matches", {}).items():
        rated = sorted(
            [(pid, p) for pid, p in md.get("player_stats", {}).items() if p.get("rating")],
            key=lambda x: x[1].get("rating", 0), reverse=True
        )
        top5 = [{"name": p["name"], "rating": round(p["rating"], 1),
                 "mins": p["mins"], "goals": p.get("goals", 0), "assists": p.get("assists", 0),
                 "team": md["home"] if p["is_home"] else md["away"]}
                for _, p in rated[:5] if p.get("name")]
        goals = [{"name": g.get("player_name", "?"), "min": int(g.get("minute", 0)),
                  "type": g.get("type", "open_play"),
                  "team": md["home"] if g.get("is_home") else md["away"]}
                 for g in md.get("incidents", {}).get("goals", []) if not g.get("is_own_goal")]
        suspensions = [{"name": s.get("player_name", "?"),
                        "team": md["home"] if s.get("is_home") else md["away"]}
                       for s in md.get("incidents", {}).get("missing_next", [])]
        wc_fecha1.append({
            "eid": int(eid_str), "group": md.get("group", ""), "round_num": md.get("round_num", 1),
            "home": md["home"], "away": md["away"],
            "sh": md.get("score_home"), "sa": md.get("score_away"),
            "top": top5, "goals": goals, "suspensions": suspensions,
            "atk_home": wc_team_profiles.get(md["home"], {}).get("attack_zones", {}),
            "atk_away": wc_team_profiles.get(md["away"], {}).get("attack_zones", {}),
        })
    wc_fecha1.sort(key=lambda x: (x["group"], x["eid"]))

    DATA = {
        "fixtures":        fixtures,
        "players":         player_list,
        "team_stats":      team_stats,
        "fdr_table":       fdr_table,
        "fm_scoring":      FM,
        "pos_avgs":        pos_avgs,
        "fecha":           args.fecha,
        "predictions":     predictions,
        "coaches":         coaches,
        "wc_team_profiles": wc_team_profiles,
        "wc_fecha1": wc_fecha1,
    }

    data_json = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))

    # Equipos sin team_stats (sus stats de ataque/defensa defaultean a promedio)
    with open(BASE_DIR / "wc2026_squads.json", encoding="utf-8") as f:
        squads_all = json.load(f)
    missing_teams = sorted(
        name for name, data in squads_all.items()
        if name not in team_stats or len(data.get("players", [])) < 20
    )

    # ── HTML ───────────────────────────────────────────────────────────────────
    html = build_html(data_json, args.fecha, missing_teams)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard guardado: {OUT_PATH}")

    # Print top 20
    print("\n=== TOP 20 xPts ===")
    print(f"{'#':>3}  {'Jugador':<26} {'Sel':<20} {'Pos':>3}  {'xPts':>5}  {'P(G)%':>6}  {'P(VI)%':>7}  {'Rival'}")
    print("    " + "-"*90)
    for i, p in enumerate(player_list[:20], 1):
        loc = "vs" if not p["is_home"] else "v/"
        print(f"  {i:>2}  {p['name']:<26} {p['team']:<20} {p['pos']:>3}  "
              f"{p['xpts']:>5.2f}  {p['p_goal']:>5.1f}%  {p['p_cs']:>6.1f}%  "
              f"{loc} {p['opp']}")


def build_html(data_json, fecha, missing_teams=None):
    fecha_label = f" — Fecha {fecha}" if fecha else " — Fase de Grupos"
    missing_html = ""
    if missing_teams:
        items = "  ·  ".join(missing_teams)
        missing_html = f'<div style="background:#1e1a0a;border:1px solid #78350f;border-radius:8px;padding:10px 16px;margin-bottom:16px;font-size:12px;color:#fbbf24"><strong>⚠ Sin datos de equipo (stats defaultean a promedio):</strong>  {items}</div>'
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mundial 2026 | Fantasy Analytics{fecha_label}</title>
<style>
  :root {{
    --bg: #0a0e1a; --card: #111827; --border: #1e2d40; --accent: #3b82f6;
    --gold: #f59e0b; --green: #10b981; --red: #ef4444; --text: #e2e8f0;
    --muted: #6b7280; --pos-g: #8b5cf6; --pos-d: #3b82f6;
    --pos-m: #10b981; --pos-f: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; }}

  /* Header */
  .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f2540 100%);
    border-bottom: 1px solid var(--border); padding: 20px 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; color: #fff; }}
  .header .sub {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}

  /* Layout */
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px 32px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .card-title {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); margin-bottom: 14px; font-weight: 600; }}

  /* Filters */
  .filters {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }}
  .filter-btn {{ padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--card); color: var(--text); cursor: pointer; font-size: 12px;
    transition: all .15s; }}
  .filter-btn.active, .filter-btn:hover {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  input[type="text"] {{ padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--card); color: var(--text); font-size: 13px; width: 200px; }}
  select.f-select {{ padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--card); color: var(--text); font-size: 12px; cursor: pointer; }}
  /* Captain panel */
  .cap-panel {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 20px; margin-bottom: 20px; }}
  .cap-panel-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--gold); font-weight: 700; margin-bottom: 12px; }}
  .cap-list {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .cap-card {{ background: #1a2535; border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 14px; min-width: 160px; position: relative; }}
  .cap-card .cap-rank {{ position: absolute; top: 8px; right: 10px; font-size: 18px;
    font-weight: 900; color: var(--border); }}
  .cap-card .cap-name {{ font-size: 13px; font-weight: 700; margin-bottom: 2px; }}
  .cap-card .cap-meta {{ font-size: 11px; color: var(--muted); }}
  .cap-card .cap-xpts {{ font-size: 20px; font-weight: 900; color: var(--gold); margin-top: 4px; }}
  .cap-card .cap-badge {{ display:inline-block; background: var(--gold); color: #000;
    border-radius: 4px; font-size: 10px; font-weight: 800; padding: 1px 6px; margin-right: 4px; }}

  /* Table */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #0d1525; color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border);
    white-space: nowrap; cursor: pointer; user-select: none; }}
  th:hover {{ color: var(--text); }}
  tr {{ border-bottom: 1px solid #151f30; transition: background .1s; }}
  tr:hover {{ background: #141e30; }}
  td {{ padding: 9px 12px; }}

  /* Pos badges */
  .pos {{ display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .pos-G {{ background: #3b1f6e; color: var(--pos-g); }}
  .pos-D {{ background: #1a2f5a; color: var(--pos-d); }}
  .pos-M {{ background: #0f3028; color: var(--pos-m); }}
  .pos-F {{ background: #3d2a00; color: var(--pos-f); }}

  /* xPts bar */
  .xpts-bar {{ display: flex; align-items: center; gap: 8px; }}
  .bar {{ height: 6px; border-radius: 3px; background: var(--accent); min-width: 2px; }}

  /* FDR dots */
  .fdr {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; }}
  .fdr-1 {{ background: #ef4444; }}
  .fdr-2 {{ background: #f97316; }}
  .fdr-3 {{ background: #eab308; }}
  .fdr-4 {{ background: #84cc16; }}
  .fdr-5 {{ background: #10b981; }}

  /* Cap badge */
  .cap {{ background: var(--gold); color: #000; border-radius: 4px;
    font-size: 10px; font-weight: 700; padding: 1px 5px; }}

  /* Group tag */
  .group-tag {{ background: #1e2d40; border-radius: 4px; font-size: 10px;
    font-weight: 600; padding: 2px 6px; color: var(--muted); }}

  /* Form dot */
  .form-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block;
    background: var(--green); margin-right: 4px; }}

  /* FDR Table */
  .fdr-table {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }}
  .fdr-row {{ display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px; background: #0d1525; border-radius: 8px; }}
  .fdr-name {{ font-size: 13px; }}
  .fdr-score {{ font-size: 12px; color: var(--muted); }}

  /* Sortable highlight */
  th.sort-asc::after  {{ content: " ▲"; color: var(--accent); }}
  th.sort-desc::after {{ content: " ▼"; color: var(--accent); }}

  /* DT Panel */
  .dt-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 10px; }}
  .dt-match {{ background: #0d1525; border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }}
  .dt-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .dt-group {{ font-size: 10px; font-weight: 700; color: var(--muted); background: #1e2d40;
    border-radius: 4px; padding: 2px 6px; }}
  .dt-teams {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .dt-team {{ text-align: center; flex: 1; }}
  .dt-team-name {{ font-size: 13px; font-weight: 700; }}
  .dt-ev {{ font-size: 20px; font-weight: 900; margin-top: 2px; }}
  .dt-ev.pos {{ color: var(--green); }}
  .dt-ev.neg {{ color: var(--red); }}
  .dt-ev.neu {{ color: var(--muted); }}
  .dt-vs {{ font-size: 11px; color: var(--muted); padding: 0 8px; }}
  .dt-probs {{ display: flex; gap: 4px; margin-top: 6px; }}
  .dt-prob-bar {{ flex: 1; background: #1e2d40; border-radius: 4px; padding: 4px 6px;
    text-align: center; font-size: 11px; }}
  .dt-lambda {{ font-size: 10px; color: var(--muted); margin-top: 4px; text-align: center; }}
  .dt-score-row {{ display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }}
  .dt-score-chip {{ font-size: 10px; background: #1a2535; border-radius: 3px;
    padding: 2px 5px; color: var(--muted); }}
  .dt-score-chip.top {{ background: #0f3028; color: var(--green); font-weight: 700; }}

  /* Team strength table */
  .ts-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }}
  .ts-row {{ background: #0d1525; border-radius: 8px; padding: 8px 12px;
    display: flex; justify-content: space-between; align-items: center; }}
  .ts-name {{ font-size: 12px; font-weight: 600; }}
  .ts-stats {{ display: flex; gap: 8px; font-size: 11px; color: var(--muted); }}

  /* Sub-section toggles */
  .subsec-toggle {{ background: none; border: none; color: var(--muted); font-size: 12px;
    font-weight: 600; cursor: pointer; padding: 0; letter-spacing: .04em;
    text-transform: uppercase; transition: color .15s; }}
  .subsec-toggle:hover, .subsec-toggle.open {{ color: var(--accent); }}

  /* DT top EVs */
  .dt-top-list {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .dt-top-card {{ background: #0d1525; border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 14px; min-width: 200px; flex: 1; }}
  .dt-top-match {{ font-size: 12px; font-weight: 700; margin-bottom: 4px; }}
  .dt-top-evs {{ display: flex; justify-content: space-between; font-size: 18px; font-weight: 900; }}
  .dt-top-sub {{ display: flex; justify-content: space-between; font-size: 10px;
    color: var(--muted); margin-top: 3px; }}

  @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<div class="header">
  <h1>⚽ Mundial 2026 — Fantasy Analytics{fecha_label}</h1>
  <div class="sub">xPts modelo Fantasy Manager | Scoring FM | Datos: SofaScore club 2025-26 + selecciones</div>
</div>

<div class="container">

  {missing_html}

  <!-- Fecha tabs + info panel -->
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap">
    <button class="filter-btn" id="tab-1" onclick="setFecha(1,this)">Fecha 1</button>
    <button class="filter-btn" id="tab-2" onclick="setFecha(2,this)">Fecha 2</button>
    <button class="filter-btn" id="tab-3" onclick="setFecha(3,this)">Fecha 3</button>
    <button class="filter-btn" id="tab-4" onclick="setFecha(4,this)" style="border-color:#f59e0b;color:#f59e0b">Octavos</button>
    <button class="filter-btn active" id="tab-5" onclick="setFecha(5,this)" style="border-color:#10b981;color:#10b981">Cuartos</button>
    <button class="filter-btn" id="tab-0" onclick="setFecha(0,this)">Todas</button>
    <span style="width:1px;height:24px;background:var(--border);margin:0 4px"></span>
    <button class="filter-btn" id="tab-res1" onclick="showResultsF1(this)"
      style="border-color:#a78bfa;color:#a78bfa;font-size:11px;padding:5px 10px">Resultados F1</button>
    <button class="filter-btn" onclick="toggleInfo()" id="info-toggle"
      style="border-color:var(--gold);color:var(--gold);font-size:11px;padding:5px 10px">
      ¿Cómo funciona?
    </button>
  </div>

  <!-- Panel de metodología -->
  <div id="info-panel" style="display:none;margin-bottom:20px">
    <div class="card" style="border-color:var(--gold);font-size:12px;line-height:1.7">
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px">

        <!-- Scoring -->
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);font-weight:700;margin-bottom:10px">
            Sistema de puntos (Fantasy Manager)
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:11.5px">
            <thead>
              <tr style="color:var(--muted)">
                <th style="text-align:left;padding:3px 0;font-weight:500">Evento</th>
                <th style="text-align:center;padding:3px 4px;color:var(--pos-g)">GK</th>
                <th style="text-align:center;padding:3px 4px;color:var(--pos-d)">DEF</th>
                <th style="text-align:center;padding:3px 4px;color:var(--pos-m)">MED</th>
                <th style="text-align:center;padding:3px 4px;color:var(--pos-f)">DEL</th>
              </tr>
            </thead>
            <tbody style="color:var(--text)">
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">Gol</td><td style="text-align:center;padding:3px 4px;color:var(--pos-g)">10</td><td style="text-align:center;padding:3px 4px;color:var(--pos-d)">8</td><td style="text-align:center;padding:3px 4px;color:var(--pos-m)">6</td><td style="text-align:center;padding:3px 4px;color:var(--pos-f)">5</td></tr>
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">Asistencia</td><td colspan="4" style="text-align:center;padding:3px 4px">3</td></tr>
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">Valla invicta</td><td style="text-align:center;padding:3px 4px;color:var(--pos-g)">4</td><td style="text-align:center;padding:3px 4px;color:var(--pos-d)">3</td><td style="text-align:center;padding:3px 4px;color:var(--pos-m)">1</td><td style="text-align:center;padding:3px 4px;color:var(--pos-f)">—</td></tr>
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">+60 min jugados</td><td colspan="4" style="text-align:center;padding:3px 4px">2</td></tr>
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">Gol de la victoria</td><td colspan="4" style="text-align:center;padding:3px 4px">3</td></tr>
              <tr style="border-top:1px solid var(--border)"><td style="padding:3px 0">Cada 3 atajadas</td><td style="text-align:center;padding:3px 4px;color:var(--pos-g)">1</td><td colspan="3" style="text-align:center;padding:3px 4px;color:var(--muted)">—</td></tr>
              <tr style="border-top:1px solid var(--border);color:var(--red)"><td style="padding:3px 0">Amarilla</td><td colspan="4" style="text-align:center;padding:3px 4px">−1</td></tr>
              <tr style="border-top:1px solid var(--border);color:var(--red)"><td style="padding:3px 0">Roja</td><td colspan="4" style="text-align:center;padding:3px 4px">−3</td></tr>
            </tbody>
          </table>
        </div>

        <!-- xPts -->
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);font-weight:700;margin-bottom:10px">
            Cómo se calcula xPts
          </div>
          <div style="color:var(--muted);margin-bottom:8px">
            xPts es el valor esperado de puntos por partido, basado en las probabilidades individuales de cada evento:
          </div>
          <div style="background:var(--bg);border-radius:8px;padding:10px 12px;margin-bottom:10px;font-family:monospace;font-size:11px;color:var(--text);line-height:1.8">
            xPts = (<span style="color:var(--pos-f)">p_gol</span> × pts_gol)<br>
            &nbsp;&nbsp;&nbsp;&nbsp; + (<span style="color:var(--green)">p_asist</span> × 3)<br>
            &nbsp;&nbsp;&nbsp;&nbsp; + (<span style="color:var(--pos-d)">p_valla</span> × pts_valla)<br>
            &nbsp;&nbsp;&nbsp;&nbsp; + (<span style="color:var(--accent)">p_juega</span> × 2)<br>
            &nbsp;&nbsp;&nbsp;&nbsp; + BPR<br>
            &nbsp;&nbsp;&nbsp;&nbsp; × <span style="color:var(--accent)">p_juega</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;font-size:11.5px">
            <div><span style="color:var(--pos-f);font-weight:600">p_gol</span> — xG/90 del jugador × dificultad rival × localía</div>
            <div><span style="color:var(--green);font-weight:600">p_asist</span> — xA/90 del jugador × mismo ajuste</div>
            <div><span style="color:var(--pos-d);font-weight:600">p_valla</span> — lambda del rival (modelo Dixon-Coles) convertido a prob. de CS</div>
            <div><span style="color:var(--accent);font-weight:600">p_juega</span> — prob. de jugar 60+ min basada en minutos internacionales recientes</div>
            <div><span style="color:var(--gold);font-weight:600">BPR</span> — bonus por rating Plackett-Luce: EV de ser figura del partido (3/2/1 pts top-3)</div>
          </div>
        </div>

        <!-- Ajustes -->
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);font-weight:700;margin-bottom:10px">
            Ajustes del modelo
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;font-size:11.5px">
            <div>
              <div style="color:var(--text);font-weight:600;margin-bottom:2px">Calidad del rival (FDR)</div>
              <div style="color:var(--muted)">Beta del modelo Dixon-Coles: equipos con beta bajo son difíciles de atacar (FDR 1 = rojo).</div>
            </div>
            <div>
              <div style="color:var(--text);font-weight:600;margin-bottom:2px">Localía</div>
              <div style="color:var(--muted)">+15% para EE.UU./Canadá/México (sedes reales). +3% local, −3% visitante para el resto.</div>
            </div>
            <div>
              <div style="color:var(--text);font-weight:600;margin-bottom:2px">Arquetipo de jugador</div>
              <div style="color:var(--muted)">Se ajusta xG/xA según el tipo (rematador, enganche, extremo, etc.) y la zona vulnerable del rival (box vs wide).</div>
            </div>
            <div>
              <div style="color:var(--text);font-weight:600;margin-bottom:2px">Capitán</div>
              <div style="color:var(--muted)">cap_score = xPts × 2 (si sale titular). La recomendación combina xPts alto con alta probabilidad de jugar.</div>
            </div>
            <div>
              <div style="color:var(--text);font-weight:600;margin-bottom:2px">Posiciones</div>
              <div style="color:var(--muted)">Según Fantasy Manager AR. Algunos jugadores tienen override manual (ej: Kimmich → DEF, Neymar → MED).</div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <script>
    function toggleInfo() {{
      const p = document.getElementById('info-panel');
      const b = document.getElementById('info-toggle');
      const open = p.style.display === 'none';
      p.style.display = open ? 'block' : 'none';
      b.style.background = open ? 'rgba(245,158,11,0.12)' : '';
    }}
  </script>

  <!-- Captain recommendations -->
  <div id="main-view">
  <div class="cap-panel">
    <div class="cap-panel-title">⭐ Capitanes recomendados</div>
    <div class="cap-list" id="cap-list"></div>
  </div>


  <!-- Panel Resultados F1 -->
  <div id="results-f1-panel" style="display:none">
    <div id="res-f1-summary" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px"></div>
    <div id="res-f1-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px"></div>
  </div>

  <!-- DT Panel -->
  <div class="card" style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <div class="card-title" style="margin-bottom:0">🏆 Panel DT — Diferencia de Goles Esperada (Dixon-Coles)</div>
      <div style="font-size:11px;color:var(--muted)">EV positivo = local favorito · negativo = visitante favorito</div>
    </div>

    <!-- Top EVs siempre visibles -->
    <div id="dt-top"></div>

    <!-- Sub-sección predicciones por partido -->
    <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px">
      <button class="subsec-toggle" onclick="toggleSub('dt-matches', this)">
        ▶ Predicciones por partido
      </button>
      <div id="dt-matches" class="subsec-body" style="display:none;margin-top:10px">
        <div id="dt-panel"></div>
      </div>
    </div>

  </div>

  <!-- Filters -->
  <div class="filters">
    <button class="filter-btn active" onclick="filterPos(null,this)">Todos</button>
    <button class="filter-btn" onclick="filterPos('G',this)">GK</button>
    <button class="filter-btn" onclick="filterPos('D',this)">DEF</button>
    <button class="filter-btn" onclick="filterPos('M',this)">MED</button>
    <button class="filter-btn" onclick="filterPos('F',this)">DEL</button>
    <span style="width:1px;height:24px;background:var(--border);margin:0 4px"></span>
    <select class="f-select" id="sel-pais" onchange="refresh()">
      <option value="">Todos los países</option>
    </select>
    <select class="f-select" id="sel-grupo" onchange="refresh()">
      <option value="">Todos los grupos</option>
    </select>
    <span style="flex:1"></span>
    <input type="text" id="search" placeholder="Buscar jugador..." oninput="refresh()">
  </div>

  <!-- Main table -->
  <div class="card" style="margin-bottom:24px">
    <div class="card-title">Proyecciones xPts por jugador</div>
    <div class="table-wrap">
      <table id="main-table">
        <thead>
          <tr>
            <th onclick="sortTable(0)">#</th>
            <th onclick="sortTable(1)">Jugador</th>
            <th onclick="sortTable(2)">Selección</th>
            <th>Gr</th>
            <th onclick="sortTable(4)">Pos</th>
            <th onclick="sortTable(5)">Club</th>
            <th onclick="sortTable(6)">Rival</th>
            <th onclick="sortTable(7)">xPts ▼</th>
            <th onclick="sortTable(8)">P(Gol)%</th>
            <th onclick="sortTable(9)">P(Asist)%</th>
            <th onclick="sortTable(10)">P(VI)%</th>
            <th onclick="sortTable(11)">xG/90</th>
            <th onclick="sortTable(12)">xA/90</th>
            <th onclick="sortTable(13)">PJ club</th>
            <th>Forma</th>
            <th>Lineup</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
  </div>

  <!-- FDR + Grupos -->
  <div class="grid-2">
    <div class="card">
      <div class="card-title">FDR — Dificultad Defensiva (1 = difícil atacar · 5 = fácil)</div>
      <div class="fdr-table" id="fdr-table"></div>
    </div>
    <div class="card">
      <div class="card-title">Fixture por Grupo</div>
      <div id="fixtures-list" style="max-height:400px;overflow-y:auto"></div>
    </div>
  </div>

</div>

  </div><!-- /main-view -->
</div><!-- /container -->
<script>
const D = {data_json};
let activePos   = null;
let activeGroup = null;
let activeFecha = 5;
let sortCol     = 7;
let sortDir     = 1;

function showResultsF1(btn) {{
  document.querySelectorAll("[id^='tab-']").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  var mv = document.getElementById("main-view");
  var rf = document.getElementById("results-f1-panel");
  if (mv) mv.style.display = "none";
  if (rf) rf.style.display = "block";
  renderResultsF1();
}}

function showMainView() {{
  var mv = document.getElementById("main-view");
  var rf = document.getElementById("results-f1-panel");
  if (mv) mv.style.display = "block";
  if (rf) rf.style.display = "none";
}}

function setFecha(n, btn) {{
  showMainView();
  activeFecha = n;
  document.querySelectorAll("[id^='tab-']").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  refresh();
  renderCaptains();
  renderDTTop();
  renderDTPanel();
}}

// ── Render ──────────────────────────────────────────────────────────────────
function posClass(p) {{ return `pos pos-${{p}}`; }}
function fdrDot(fdr) {{ return `<span class="fdr fdr-${{fdr}}"></span>`; }}

function renderTable(players) {{
  const body = document.getElementById("table-body");
  let maxXpts = 0;
  for (let i = 0; i < players.length; i++) {{ if ((players[i].xpts||0) > maxXpts) maxXpts = players[i].xpts; }}
  if (maxXpts === 0) maxXpts = 0.01;
  const rows = players.map((p, i) => {{
    const loc  = p.is_home ? "vs" : "@";
    const xbar = Math.round((p.xpts / maxXpts) * 80);
    const fdr  = fdrDot(p.fdr_opp || 3);
    const cap  = i === 0 ? '<span class="cap">C</span> ' : "";
    const form = p.has_form ? '<span class="form-dot"></span>' : '<span style="opacity:.3">·</span>';
    let roleCell = p.role || "—";
    if (p.lineup_status === "starter")    roleCell = '<span style="color:var(--green);font-size:11px">✓ Titular</span>';
    else if (p.lineup_status === "substitute") roleCell = '<span style="color:var(--muted);font-size:11px">~ Suplente</span>';
    else if (p.lineup_status === "missing")    roleCell = '<span style="color:var(--red);font-size:11px">✗ Baja</span>';
    const spIcons = (p.sp_roles||[]).map(r => {{
      if (r==="pk_primary")   return '<span title="PK titular" style="font-size:10px;background:#7c3aed;color:#fff;border-radius:3px;padding:1px 4px">PK</span>';
      if (r==="pk_secondary") return '<span title="PK alt" style="font-size:10px;background:#4c1d95;color:#c4b5fd;border-radius:3px;padding:1px 4px">pk</span>';
      if (r==="fk_primary")   return '<span title="FK titular" style="font-size:10px;background:#1d4ed8;color:#fff;border-radius:3px;padding:1px 4px">FK</span>';
      if (r==="fk_secondary") return '<span title="FK alt" style="font-size:10px;background:#1e3a8a;color:#93c5fd;border-radius:3px;padding:1px 4px">fk</span>';
      if (r==="ck_primary")   return '<span title="CK" style="font-size:10px;background:#065f46;color:#fff;border-radius:3px;padding:1px 4px">CK</span>';
      return "";
    }}).join(" ");
    return `<tr data-pos="${{p.pos}}" data-group="${{p.group}}" data-name="${{p.name.toLowerCase()}}">
        <td style="color:var(--muted)">${{i+1}}</td>
        <td>${{cap}}<strong>${{p.name}}</strong> ${{spIcons}}</td>
        <td style="font-size:12px;color:var(--muted)">${{p.team}}</td>
        <td><span class="group-tag">${{p.group}}</span></td>
        <td><span class="${{posClass(p.pos)}}">${{p.pos}}</span></td>
        <td style="font-size:11px;color:var(--muted)">${{p.club || "—"}}</td>
        <td style="font-size:12px">${{fdr}} ${{loc}} ${{p.opp}}</td>
        <td>
          <div class="xpts-bar">
            <strong style="min-width:36px">${{(p.xpts||0).toFixed(2)}}</strong>
            <div class="bar" style="width:${{xbar}}px"></div>
          </div>
        </td>
        <td style="color:var(--pos-f)">${{(p.p_goal||0).toFixed(1)}}%</td>
        <td style="color:var(--pos-m)">${{(p.p_assist||0).toFixed(1)}}%</td>
        <td style="color:var(--pos-d)">${{(p.p_cs||0).toFixed(1)}}%</td>
        <td style="color:var(--muted)">${{(p.xg90||0).toFixed(3)}}</td>
        <td style="color:var(--muted)">${{(p.xa90||0).toFixed(3)}}</td>
        <td style="color:var(--muted)">${{p.club_games||0}}</td>
        <td>${{form}}</td>
        <td>${{roleCell}}</td>
      </tr>`;
  }});
  body.innerHTML = rows.join("");
}}

function renderFDR() {{
  const el = document.getElementById("fdr-table");
  el.innerHTML = D.fdr_table.map(t => {{
    const col = ["","#ef4444","#f97316","#eab308","#84cc16","#10b981"][t.fdr||3];
    return `<div class="fdr-row">
      <span class="fdr-name">[${{{{"A":1,"B":2,"C":3,"D":4,"E":5,"F":6,"G":7,"H":8,"I":9,"J":10,"K":11,"L":12}}[t.group]||"?"}}] ${{t.team}}</span>
      <span class="fdr-score" style="color:${{col}}">FDR ${{t.fdr}} · def=${{(t.def_score||50).toFixed(0)}}</span>
    </div>`;
  }}).join("");
}}

function renderFixtures() {{
  const el = document.getElementById("fixtures-list");
  const groups = {{}};
  D.fixtures.forEach(f => {{
    if (!groups[f.group]) groups[f.group] = [];
    groups[f.group].push(f);
  }});
  el.innerHTML = Object.entries(groups).map(([g, fxs]) => `
    <div style="margin-bottom:12px">
      <div style="font-size:11px;font-weight:700;color:var(--muted);margin-bottom:4px">GRUPO ${{g}}</div>
      ${{fxs.map(f => {{
        const dt = f.timestamp ? new Date(f.timestamp*1000).toLocaleDateString("es",{{day:"2-digit",month:"2-digit"}}) : "—";
        const score = f.score_home != null ? ` ${{f.score_home}}-${{f.score_away}}` : "";
        return `<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
          <span>${{f.home_name}} vs ${{f.away_name}}</span>
          <span style="color:var(--muted)">${{score||dt}}</span>
        </div>`;
      }}).join("")}}
    </div>
  `).join("");
}}

function buildSelects() {{
  // Ordenar selecciones por xpts máximo de sus jugadores (mayor primero)
  const teamMax = {{}};
  D.players.forEach(p => {{ if ((p.xpts||0) > (teamMax[p.team]||0)) teamMax[p.team] = p.xpts; }});
  const teams  = [...new Set(D.players.map(p => p.team))].sort((a,b) => (teamMax[b]||0) - (teamMax[a]||0));
  const groups = [...new Set(D.players.map(p => p.group))].sort();
  const selP = document.getElementById("sel-pais");
  const selG = document.getElementById("sel-grupo");
  teams.forEach(t  => selP.appendChild(Object.assign(document.createElement("option"), {{value: t, textContent: t}})));
  groups.forEach(g => selG.appendChild(Object.assign(document.createElement("option"), {{value: g, textContent: "Grupo " + g}})));
}}

// ── Filters ──────────────────────────────────────────────────────────────────
function getFiltered() {{
  let pl = D.players;
  if (activeFecha) pl = pl.filter(p => p.round_num === activeFecha);
  if (activePos)   pl = pl.filter(p => p.pos === activePos);
  const gv = document.getElementById("sel-grupo").value;
  const pv = document.getElementById("sel-pais").value;
  if (gv) pl = pl.filter(p => p.group === gv);
  if (pv) pl = pl.filter(p => p.team === pv);
  const q = document.getElementById("search").value.toLowerCase().trim();
  if (q) pl = pl.filter(p => p.name.toLowerCase().includes(q) ||
    p.team.toLowerCase().includes(q) || p.opp.toLowerCase().includes(q));

  return pl;
}}

function filterPos(pos, btn) {{
  activePos = pos;
  document.querySelectorAll(".filters .filter-btn").forEach(b => {{
    if (["Todos","GK","DEF","MED","DEL"].includes(b.textContent)) b.classList.remove("active");
  }});
  btn.classList.add("active");
  refresh();
}}

// ── Captain recommendations ───────────────────────────────────────────────────
function renderCaptains() {{
  // Top 1 por posición (GK, DEF, MED, FWD) para la fecha activa
  let pool = D.players;
  if (activeFecha) pool = pool.filter(p => p.round_num === activeFecha);
  pool = [...pool].sort((a,b) => (b.xpts||0) - (a.xpts||0));

  const POS_ORDER = ["G","D","M","F"];
  const POS_LABEL = {{ G:"GK", D:"DEF", M:"MED", F:"DEL" }};
  const POS_EMOJI = {{ G:"🧤", D:"🛡️", M:"⚙️", F:"⚡" }};
  const best = {{}};
  const seenPlayer = new Set();
  for (const p of pool) {{
    const key = p.player_id + "_" + p.team;
    if (seenPlayer.has(key)) continue;
    seenPlayer.add(key);
    if (!best[p.pos]) best[p.pos] = p;
    if (POS_ORDER.every(pos => best[pos])) break;
  }}

  const el = document.getElementById("cap-list");
  el.innerHTML = POS_ORDER.map(pos => {{
    const p = best[pos];
    if (!p) return "";
    const loc = p.is_home ? "vs" : "@";
    return `<div class="cap-card">
      <div class="cap-rank">${{POS_EMOJI[pos]}}</div>
      <div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">${{POS_LABEL[pos]}}</div>
      <div class="cap-name"><span class="cap-badge">C</span>${{p.name}}</div>
      <div class="cap-meta"><span class="pos pos-${{p.pos}}" style="font-size:10px;padding:1px 5px">${{p.pos}}</span> ${{p.team}}</div>
      <div class="cap-meta" style="margin-top:2px">${{loc}} ${{p.opp}} · Gr ${{p.group}}</div>
      <div class="cap-xpts">${{(p.xpts||0).toFixed(2)}} xPts</div>
    </div>`;
  }}).join("");
}}

function refresh() {{
  const pl = getFiltered();
  pl.sort((a,b) => (a[colKey(sortCol)]||0) < (b[colKey(sortCol)]||0) ? sortDir : -sortDir);
  renderTable(pl);
  renderCaptains();
}}

// ── Sort ─────────────────────────────────────────────────────────────────────
const COL_KEYS = [null,"name","team","group","pos","club","opp","xpts","p_goal","p_assist","p_cs","xg90","xa90","club_games"];
function colKey(i) {{ return COL_KEYS[i] || "xpts"; }}

function sortTable(col) {{
  if (sortCol === col) sortDir *= -1;
  else {{ sortCol = col; sortDir = 1; }}
  document.querySelectorAll("th").forEach((th,i) => {{
    th.classList.remove("sort-asc","sort-desc");
    if (i === col) th.classList.add(sortDir === 1 ? "sort-desc" : "sort-asc");
  }});
  refresh();
}}

// ── Sub-section toggle ───────────────────────────────────────────────────────
function toggleSub(id, btn) {{
  const el = document.getElementById(id);
  const open = el.style.display !== "none";
  el.style.display = open ? "none" : "block";
  btn.classList.toggle("open", !open);
  btn.textContent = (open ? "▶" : "▼") + btn.textContent.slice(1);
}}

// ── DT Panel ─────────────────────────────────────────────────────────────────
function evClass(ev) {{
  if (ev > 0.3) return "pos";
  if (ev < -0.3) return "neg";
  return "neu";
}}

function renderDTTop() {{
  const pred    = D.predictions || {{}};
  const coaches = D.coaches || {{}};
  const fixtures = (pred.fixtures || []).filter(f => !activeFecha || f.round === activeFecha);

  // Construir lista de DTs: un entry por equipo (home y away) con su EV
  const dtList = [];
  fixtures.forEach(f => {{
    const coachH = coaches[f.home];
    const coachA = coaches[f.away];
    if (coachH) dtList.push({{ coach: coachH.name, team: f.home, opp: f.away,  ev: f.ev_home_dt, is_home: true,  f }});
    if (coachA) dtList.push({{ coach: coachA.name, team: f.away, opp: f.home,  ev: f.ev_away_dt, is_home: false, f }});
  }});
  dtList.sort((a, b) => b.ev - a.ev);
  const top = dtList.slice(0, 8);

  const el = document.getElementById("dt-top");
  if (!el) return;
  if (top.length === 0) {{ el.innerHTML = '<p style="color:var(--muted);font-size:13px">Sin datos</p>'; return; }}

  const medals = ["🥇","🥈","🥉","4°","5°","6°","7°","8°"];
  el.innerHTML = '<div class="dt-top-list">' + top.map((d, i) => {{
    const ev = (d.ev||0).toFixed(2);
    const loc = d.is_home ? "vs" : "@";
    const ph = ((d.f.p_home_win||0)*100).toFixed(0);
    const pd = ((d.f.p_draw||0)*100).toFixed(0);
    const pa = ((d.f.p_away_win||0)*100).toFixed(0);
    const winPct = d.is_home ? ph : pa;
    return `<div class="dt-top-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-size:10px;color:var(--muted);font-weight:700;margin-bottom:2px">${{medals[i]}} DT</div>
          <div style="font-size:14px;font-weight:800">${{d.coach}}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:1px">${{d.team}} ${{loc}} ${{d.opp}}</div>
        </div>
        <div style="text-align:right">
          <div class="dt-ev ${{evClass(d.ev)}}" style="font-size:22px;font-weight:900">${{ev > 0 ? '+' : ''}}${{ev}}</div>
          <div style="font-size:10px;color:var(--muted)">EV goles</div>
        </div>
      </div>
      <div class="dt-top-sub" style="margin-top:6px">
        <span>L ${{ph}}%</span><span>E ${{pd}}%</span><span>V ${{pa}}%</span>
        <span style="margin-left:auto;color:var(--green)">${{winPct}}% ganar</span>
      </div>
    </div>`;
  }}).join("") + '</div>';
}}

function renderDTPanel() {{
  const pred = D.predictions || {{}};
  const fixtures = (pred.fixtures || []).filter(f => !activeFecha || f.round === activeFecha);
  const sorted = [...fixtures].sort((a, b) => Math.abs(b.ev_home_dt) - Math.abs(a.ev_home_dt));

  const el = document.getElementById("dt-panel");
  if (!el || sorted.length === 0) {{ if(el) el.innerHTML = '<p style="color:var(--muted);font-size:13px">Sin predicciones disponibles</p>'; return; }}

  el.innerHTML = '<div class="dt-grid">' + sorted.map(f => {{
    const topScores = Object.entries(f.score_dist || {{}})
      .sort((a,b) => b[1] - a[1]).slice(0, 3);
    const scoresHtml = topScores.map((s, i) =>
      `<span class="dt-score-chip ${{i===0?'top':''}}">${{s[0]}} ${{(s[1]*100).toFixed(0)}}%</span>`
    ).join("");

    const lhStr = (f.lambda_home||0).toFixed(2);
    const laStr = (f.lambda_away||0).toFixed(2);
    const phStr = ((f.p_home_win||0)*100).toFixed(0);
    const pdStr = ((f.p_draw||0)*100).toFixed(0);
    const paStr = ((f.p_away_win||0)*100).toFixed(0);

    const evH = (f.ev_home_dt||0).toFixed(2);
    const evA = (f.ev_away_dt||0).toFixed(2);

    return `<div class="dt-match">
      <div class="dt-header">
        <span class="dt-group">Gr ${{f.group}} · F${{f.round}}</span>
        <span style="font-size:10px;color:var(--muted)">λ ${{lhStr}} – ${{laStr}}</span>
      </div>
      <div class="dt-teams">
        <div class="dt-team">
          <div class="dt-team-name">${{f.home}}</div>
          <div class="dt-ev ${{evClass(f.ev_home_dt)}}">${{evH > 0 ? '+' : ''}}${{evH}}</div>
        </div>
        <div class="dt-vs">vs</div>
        <div class="dt-team">
          <div class="dt-team-name">${{f.away}}</div>
          <div class="dt-ev ${{evClass(f.ev_away_dt)}}">${{evA > 0 ? '+' : ''}}${{evA}}</div>
        </div>
      </div>
      <div class="dt-probs">
        <div class="dt-prob-bar" style="color:#10b981">${{phStr}}% L</div>
        <div class="dt-prob-bar">${{pdStr}}% E</div>
        <div class="dt-prob-bar" style="color:#f59e0b">${{paStr}}% V</div>
      </div>
      <div class="dt-score-row">${{scoresHtml}}</div>
    </div>`;
  }}).join("") + '</div>';
}}

function renderTeamStrength() {{
  const pred = D.predictions || {{}};
  const params = pred.team_params || {{}};
  const teams = Object.entries(params)
    .sort((a, b) => b[1].alpha - a[1].alpha);

  const el = document.getElementById("team-strength-panel");
  if (!el) return;

  el.innerHTML = '<div class="ts-grid">' + teams.map(([name, p]) => {{
    const alphaColor = p.alpha > 1.2 ? '#10b981' : p.alpha > 0.9 ? '#f59e0b' : '#ef4444';
    const betaColor  = p.beta  < 0.6 ? '#10b981' : p.beta  < 0.9 ? '#f59e0b' : '#ef4444';
    return `<div class="ts-row">
      <span class="ts-name">${{name}}</span>
      <span class="ts-stats">
        <span style="color:${{alphaColor}}" title="Ataque (>1 = por encima de la media)">ATK ${{p.alpha.toFixed(2)}}</span>
        <span style="color:${{betaColor}}" title="Defensa (<1 = buena)">DEF ${{p.beta.toFixed(2)}}</span>
      </span>
    </div>`;
  }}).join("") + '</div>';
}}

// ── Init ─────────────────────────────────────────────────────────────────────
buildSelects();
refresh();
renderFDR();
renderFixtures();
renderDTTop();
renderDTPanel();
renderTeamStrength();

function renderResultsF1() {{
  const matches = D.wc_fecha1 || [];

  // Summary
  const totalGoals = matches.reduce((s,m) => s + (m.goals||[]).length, 0);
  const totalSusp  = matches.reduce((s,m) => s + (m.suspensions||[]).length, 0);
  const homeWins   = matches.filter(m => m.sh > m.sa).length;
  const draws      = matches.filter(m => m.sh === m.sa).length;
  const awayWins   = matches.filter(m => m.sh < m.sa).length;
  const sumEl = document.getElementById("res-f1-summary");
  if (sumEl) sumEl.innerHTML = [
    `<div class="card" style="padding:10px 16px;min-width:90px;text-align:center"><div style="font-size:22px;font-weight:900;color:var(--pos-f)">${{totalGoals}}</div><div style="font-size:10px;color:var(--muted);text-transform:uppercase">Goles</div></div>`,
    `<div class="card" style="padding:10px 16px;min-width:90px;text-align:center"><div style="font-size:22px;font-weight:900;color:var(--red)">${{totalSusp}}</div><div style="font-size:10px;color:var(--muted);text-transform:uppercase">Bajas F2</div></div>`,
    `<div class="card" style="padding:10px 16px;min-width:140px;text-align:center"><div style="font-size:16px;font-weight:700"><span style="color:var(--green)">${{homeWins}}L</span> <span style="color:var(--muted)">${{draws}}E</span> <span style="color:var(--red)">${{awayWins}}V</span></div><div style="font-size:10px;color:var(--muted);text-transform:uppercase">L/E/V</div></div>`,
    `<div class="card" style="padding:10px 16px;min-width:90px;text-align:center"><div style="font-size:22px;font-weight:900;color:var(--accent)">${{matches.length}}</div><div style="font-size:10px;color:var(--muted);text-transform:uppercase">Partidos</div></div>`,
  ].join("");

  const gridEl = document.getElementById("res-f1-grid");
  if (!gridEl) return;
  gridEl.innerHTML = matches.map(m => {{
    const scoreCol = m.sh > m.sa ? "var(--green)" : m.sh < m.sa ? "var(--red)" : "var(--muted)";

    const topHtml = (m.top||[]).slice(0,3).map(p => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #1e2d40;gap:4px">
        <span style="font-size:11px;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${{p.name}}<span style="color:var(--muted);font-size:10px"> (${{p.team.split(" ")[0]}})</span></span>
        <span style="font-size:13px;font-weight:700;color:var(--gold);white-space:nowrap">${{p.rating}} ${{p.goals?"⚽".repeat(Math.min(p.goals,3)):""}}${{p.assists?"🅰️".repeat(Math.min(p.assists,2)):""}}</span>
      </div>`).join("");

    const goalsHtml = (m.goals||[]).map(g =>
      `<div style="font-size:11px;padding:1px 0"><span style="color:var(--muted)">${{g.min}}'</span> ${{g.name}} <span style="color:var(--muted);font-size:10px">(${{g.team.split(" ")[0]}})</span>${{g.type==="set_piece"?' <span style="font-size:9px;background:#1e3a8a;color:#93c5fd;padding:1px 3px;border-radius:2px">SP</span>':''}}</div>`
    ).join("");

    const suspHtml = (m.suspensions||[]).map(s =>
      `<div style="font-size:11px;color:var(--red)">✗ ${{s.name}} <span style="color:var(--muted);font-size:10px">(${{s.team.split(" ")[0]}})</span></div>`
    ).join("");

    const atk = m.atk_home || {{}};
    const zoneBar = atk.left !== undefined ? `
      <div style="margin-top:8px;padding-top:6px;border-top:1px solid var(--border)">
        <div style="font-size:9px;color:var(--muted);margin-bottom:3px">ATK ${{m.home.split(" ")[0]}}: Izq ${{((atk.left||0)*100).toFixed(0)}}% · Cen ${{((atk.center||0)*100).toFixed(0)}}% · Der ${{((atk.right||0)*100).toFixed(0)}}%</div>
        <div style="display:flex;gap:2px;height:5px;border-radius:3px;overflow:hidden">
          <div style="flex:${{atk.left||0.01}};background:var(--accent)"></div>
          <div style="flex:${{atk.center||0.01}};background:var(--pos-g)"></div>
          <div style="flex:${{atk.right||0.01}};background:var(--green)"></div>
        </div>
      </div>` : "";

    return `<div class="card" style="padding:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:10px;font-weight:700;color:var(--muted)">GRUPO ${{m.group}}</span>
        ${{suspHtml ? `<span style="font-size:10px;color:var(--red)">✗ ${{(m.suspensions||[]).length}} baja(s)</span>` : ''}}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px">
        <div style="font-size:13px;font-weight:700;flex:1">${{m.home}}</div>
        <div style="font-size:26px;font-weight:900;color:${{scoreCol}};white-space:nowrap">${{m.sh}}-${{m.sa}}</div>
        <div style="font-size:13px;font-weight:700;flex:1;text-align:right">${{m.away}}</div>
      </div>
      ${{goalsHtml ? `<div style="margin-bottom:8px">${{goalsHtml}}</div>` : ''}}
      ${{suspHtml ? `<div style="margin-bottom:8px">${{suspHtml}}</div>` : ''}}
      <div style="border-top:1px solid var(--border);padding-top:8px">
        <div style="font-size:10px;color:var(--accent);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Top ratings</div>
        ${{topHtml}}
      </div>
      ${{zoneBar}}
    </div>`;
  }}).join("");
}}

</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
