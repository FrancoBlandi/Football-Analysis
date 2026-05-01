"""
fotmob_xg.py — Enriquece el Excel de LPF con xG y xA desde FotMob.

Uso:
    python fotmob_xg.py --input lpf/lpf_2026_stats.xlsx --output lpf/lpf_2026_stats.xlsx

FotMob season IDs:
    Primera LPF 2026 (Apertura): 28207
    Torneo Apertura 2025:        24590
"""

import sys
import io
import argparse
import unicodedata
import pandas as pd
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

LEAGUE_ID = 112

SEASONS = {
    'Primera LPF 2026': 28207,
    'Apertura 2025':    24590,
}

STATS_TO_FETCH = [
    ('xG',    'expected_goals'),
    ('xA',    'expected_assists'),
    ('xG/90', 'expected_goals_per_90'),
    ('xA/90', 'expected_assists_per_90'),
]


def normalize(name: str) -> str:
    if not name:
        return ''
    nfkd = unicodedata.normalize('NFKD', name.lower().strip())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def fetch_stat(page, season_id: int, stat_key: str) -> dict:
    """Devuelve {fotmob_player_id: (value, player_name, team_name)}"""
    url = f'https://data.fotmob.com/stats/{LEAGUE_ID}/season/{season_id}/{stat_key}.json'
    r = page.evaluate(f"""
        async () => {{
            const resp = await fetch('{url}');
            return resp.ok ? await resp.json() : {{}};
        }}
    """)
    result = {}
    for top_list in r.get('TopLists', []):
        for item in top_list.get('StatList', []):
            pid   = item.get('ParticiantId')
            name  = item.get('ParticipantName', '')
            team  = item.get('TeamName', '')
            value = item.get('StatValue')
            mins  = item.get('MinutesPlayed', 0)
            if pid and value is not None:
                result[pid] = {
                    'value': value,
                    'name':  name,
                    'team':  team,
                    'mins':  mins,
                    'name_norm': normalize(name),
                }
    return result


def build_lookup(stat_data: dict) -> tuple:
    """Dos índices: por fotmob_id y por nombre_normalizado."""
    by_id   = stat_data
    by_name = {}
    for pid, info in stat_data.items():
        key = (info['name_norm'], normalize(info['team']))
        by_name[key] = info['value']
        # también solo por nombre (sin equipo) como fallback
        by_name.setdefault(info['name_norm'], info['value'])
    return by_id, by_name


def match_value(row, by_name: dict):
    jugador = normalize(str(row.get('Jugador', '')))
    club    = normalize(str(row.get('Club', '')))
    # Intento 1: nombre + club
    v = by_name.get((jugador, club))
    if v is not None:
        return v
    # Intento 2: solo nombre
    return by_name.get(jugador)


def enrich_sheet(df: pd.DataFrame, page, season_id: int, sheet_name: str) -> pd.DataFrame:
    print(f'\n  [{sheet_name}] season_id={season_id}')
    lookups = {}
    for col_name, stat_key in STATS_TO_FETCH:
        raw = fetch_stat(page, season_id, stat_key)
        _, by_name = build_lookup(raw)
        lookups[col_name] = by_name
        print(f'    {col_name}: {len(raw)} jugadores en FotMob')

    for col_name, by_name in lookups.items():
        df[col_name] = df.apply(lambda row: match_value(row, by_name), axis=1)
        matched = df[col_name].notna().sum()
        print(f'    {col_name} matcheados: {matched}/{len(df)}')

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',  default='lpf/lpf_2026_stats.xlsx')
    parser.add_argument('--output', default='lpf/lpf_2026_stats.xlsx')
    args = parser.parse_args()

    print('Leyendo Excel...')
    xl = pd.ExcelFile(args.input)
    sheets = {s: xl.parse(s) for s in xl.sheet_names}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ).new_page()

        print('Cargando FotMob...')
        page.goto('https://www.fotmob.com', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(1500)

        for sheet_name, season_id in SEASONS.items():
            if sheet_name not in sheets:
                print(f'  Hoja "{sheet_name}" no encontrada, saltando.')
                continue
            sheets[sheet_name] = enrich_sheet(sheets[sheet_name], page, season_id, sheet_name)

        browser.close()

    print('\nGuardando Excel...')
    with pd.ExcelWriter(args.output, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print('Listo.')
    for sheet_name in SEASONS:
        if sheet_name in sheets:
            df = sheets[sheet_name]
            for col, _ in STATS_TO_FETCH:
                if col in df.columns:
                    n = df[col].notna().sum()
                    print(f'  {sheet_name} — {col}: {n}/{len(df)} jugadores con dato')


if __name__ == '__main__':
    main()
