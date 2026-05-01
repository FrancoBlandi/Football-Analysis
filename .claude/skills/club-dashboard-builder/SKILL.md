---
name: club-dashboard-builder
description: Build executive HTML dashboards for Argentine football clubs using exclusively real public data. Use this skill whenever the user asks to build, design, create, or work on a club dashboard, BI dashboard for a football club, executive dashboard for sports management, or any analytics deliverable for an Argentine club (Vélez, Racing, Lanús, Boca, River, San Lorenzo, Independiente, etc.). Also trigger this when the user mentions sources like AFA balances, Transfermarkt data, club financial reports, socios statistics, plantel cost analysis, or any combination of football + business intelligence + Argentine clubs. The skill covers data sourcing, visualization design, and final dashboard.html delivery.
---

# Club Dashboard Builder — Argentine Football

A reusable workflow to produce executive-grade HTML dashboards for any Argentine football club. The dashboard is designed for board-level decision making (presidente, comisión directiva, secretaría técnica) — **not** scouting or tactical analysis. The angle is business intelligence: how the club performs as an institution.

## Core constraints (non-negotiable)

1. **Real data only.** Every number in the dashboard must come from a verifiable public source. No synthetic data, no estimations, no "approximate" placeholders. If a metric can't be sourced reliably, it's excluded — and it does NOT appear anywhere in the dashboard, not even as a placeholder or "pendiente" tag.
2. **Three areas only.** Plantel deportivo, Finanzas consolidadas, Socios y abonos. Don't expand scope unless the user explicitly asks.
3. **Output is a single `dashboard.html` file** that opens in any browser. No Power BI, no external dependencies beyond a CDN link for Chart.js.
4. **Audience is non-technical executives.** Visualizations must be readable in 5 seconds. No clutter, no technical jargon, no needing to filter to understand the message.

## Workflow

Follow these steps in order. Don't skip ahead.

### Step 1 — Confirm the club

Ask the user which club the dashboard is for. If they've already said it earlier in the conversation, confirm. The skill works for any AFA Primera División club but availability of public data varies. Read `references/data_sources.md` to understand what's reliably available per club.

### Step 2 — Source the data

Read `references/data_sources.md` for the full source list. Then collect data into three Excel files (one per area). The files go in `/home/claude/club-dashboard-builder/data/[club-slug]/` with names:

- `plantel.xlsx`
- `finanzas.xlsx`
- `socios.xlsx`

For data that requires web scraping (Transfermarkt, club press releases, news articles), use web_search and web_fetch. Document the source URL and date in a `Sources` sheet inside each Excel file. If a metric isn't publicly available for the chosen club, leave it out — don't invent it.

### Step 3 — Build the dashboard HTML

Read `references/visual_design.md` for layout principles, color palette, and visualization choices. Generate a single `dashboard.html` file using:

- **Chart.js** via CDN (`https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js`) for all charts
- Inline CSS — no external stylesheets
- All data embedded as JavaScript constants
- Tab navigation for the four pages (CSS show/hide, lazy chart init per tab)

The file must have exactly four tab-pages:

1. **Resumen Ejecutivo** — snapshot para el presidente
2. **Plantel Deportivo** — valor de mercado, estructura etaria, tabla de jugadores
3. **Finanzas Consolidadas** — P&L, evolución de ingresos/gastos, deuda
4. **Socios y Abonos** — evolución de masa societaria, cuota promedio, ingreso por socios

**Critical rule on missing data:** If a metric couldn't be sourced, it is completely absent from the dashboard — no placeholder card, no "pendiente" tag, no empty chart. The dashboard only shows what is confirmed. Document exclusions in the README, not in the dashboard itself.

### Step 4 — Generate supporting files

Alongside `dashboard.html`, also produce:
- Three Excel files (`plantel.xlsx`, `finanzas.xlsx`, `socios.xlsx`) with all sourced data and a `Sources` sheet each
- A `README.md` documenting included metrics, excluded metrics (and why), and source URLs
- An `informe.html` analysis document (see Step 5)

### Step 5 — Generate the analysis document (informe.html)

Create a separate `informe.html` file in the same folder as the dashboard. It must have two clearly separated sections:

**Sección 1 — Explicación de la información**
For each metric and visualization in the dashboard, explain in plain Spanish what it shows, where the data comes from, and what the number means in the context of Argentine football club management. No jargon. Write for a club president who is not a data analyst.

**Sección 2 — Insights y recomendaciones**
Analyze the actual values in the dashboard and produce concrete, actionable observations:
- What is the club doing well (strengths visible in the data)?
- What are the warning signs or risks (financial, sporting, institutional)?
- What specific actions could the board take to improve each weak area?
- Prioritize: which issues are urgent vs. medium-term?

This section must engage with the real numbers — not generic advice. If finanzas show egresos ordinarios exceeding recursos ordinarios, say so explicitly and explain the implication. If the plantel skews old or young, analyze the risk. If cuotas increased 660% in 2 years, contextualize against inflation and what that means for retention.

Style: use the same visual design language as the dashboard (Vélez colors, clean white cards, readable typography). The informe.html should look like it belongs to the same package — same header, same font, same color palette — but is a document, not a dashboard. No charts needed; use styled text blocks, highlight boxes, and clear section headers.

### Step 6 — Present to the user

Summarize in chat: which club, which sources were used, which metrics are included, which were excluded due to lack of public data. Open the HTML file in the browser automatically if possible.

## Jugadores a préstamo recibido — tratamiento obligatorio

Cuando el plantel incluye jugadores cedidos por otro club (préstamos recibidos), aplicar este tratamiento sin excepción:

### Por qué importa
Un jugador en préstamo recibido **no es un activo del club**: no puede ser vendido, y su futuro lo decide el club propietario. Tratarlo igual que a un jugador propio induce a error a la dirigencia.

### Campos de datos requeridos en el array PLANTEL
```javascript
{n:"Lucas Robertone", p:"Mediocentro", e:29, v:2000000, c:"31/12/2026",
 pr:"UD Almería",        // club propietario — omitir si es jugador propio
 oc:"~€4M"}             // monto de la opción de compra, o null si no existe
```

### CSS para badge de préstamo
```css
.bp { background: #F3E5F5; color: #7B1FA2; border: 1px dashed #AB47BC; }
```

### Función fmtPr() — reemplaza fmtC() en la tabla del plantel
```javascript
function fmtPr(j) {
  if (!j.pr) return fmtC(j.c);
  const ocTxt = j.oc
    ? `<span class="badge" style="background:#E8F5E9;color:#2E7D32;margin-left:4px">OC: ${j.oc}</span>`
    : `<span class="badge" style="background:#FFEBEE;color:#C62828;margin-left:4px">sin OC</span>`;
  return `${fmtC(j.c)} <span class="badge bp">préstamo · ${j.pr}</span> ${ocTxt}`;
}
```

### KPIs a mostrar en el tab Plantel
- **Valor Total del Plantel** — suma todos (propios + préstamos), fuente Transfermarkt
- **Valor Propiedad [Club]** — suma solo los jugadores propios (excluye préstamos recibidos)
- **Jugadores** — "X propios · Y a préstamo recibido"

### Alertas obligatorias en el tab Plantel
1. Alert naranja para contratos venciendo en ≤12 meses (jugadores propios)
2. Alert violeta para cada préstamo recibido: club propietario, vencimiento, y OC si existe

### En el informe.html
- Sección 1: explicar qué significa "préstamo recibido" y qué puede/no puede hacer el club con ese jugador
- Sección 2: insight de urgencia media/alta sobre la decisión de OC antes del vencimiento del préstamo

## Colores en gráficos del plantel — regla obligatoria

**Nunca hardcodear colores por posición en el array.** Los colores de las barras de jugadores deben derivarse siempre de los datos del jugador, no del índice en el array. Usar esta lógica en todos los gráficos de plantel (Resumen y Plantel):

```javascript
// CORRECTO — color según datos del jugador
top5.map(j => j.pr ? VIOLETA : j.c.includes('2026') ? ROJO : AZUL)

// INCORRECTO — hardcodeado por posición
[ROJO, AZUL, AZUL, AZUL, AZUL]
```

Criterio de color para jugadores:
- **Violeta** (`#7B1FA2`) — jugador a préstamo recibido (no activo del club)
- **Rojo** (`#C62828`) — contrato vence en ≤12 meses (jugador propio)
- **Naranja** (`#EF6C00`) — contrato vence en 13–24 meses
- **Azul** (color del club) — resto

Este error ocurrió al migrar el dashboard de Racing a Boca: en Racing, Carboni (préstamo, primer lugar por valor) estaba correctamente en rojo. Al copiar el array hardcodeado `[ROJO, AZUL, ...]` a Boca, Ascacíbar quedó en rojo sin razón.

## SofaScore — workflow de extracción de stats de jugadores

Para obtener ratings y estadísticas de temporada de jugadores individuales via SofaScore, usar el scraper Playwright en `.claude/skills/data-scraper/scripts/sofascore.py`.

### Paso 1 — Obtener los player IDs de SofaScore

Dos métodos:

**A) API del equipo** (para forwards/midfielders — suele estar en el response):
```
https://api.sofascore.com/api/v1/team/{team_id}/players
```
- Boca Juniors team_id: `3202`
- Racing Club team_id: `3206` (ejemplo)

**B) WebSearch individual** para jugadores que no aparecen en la API (generalmente defensores y GKs):
- Buscar: `"{nombre jugador}" sofascore site:sofascore.com`
- La URL contiene el ID: `sofascore.com/player/nombre/XXXXXX` — el número al final es el ID

El ID en la URL de SofaScore **puede diferir** del ID interno que usa la API. Usar siempre el ID de la URL del player para el scraper.

### Paso 2 — Correr el scraper

```bash
# En Windows usar `python`, no `python3`
python sofascore.py --player-id {ID} --output {nombre}_sofascore.json
```

El scraper intercepta las respuestas de la API de SofaScore via Playwright. Genera un JSON con:
- `perfil`: datos del jugador (nombre, posición, altura, pie, valor de mercado)
- `estadisticas_temporada`: array con stats por torneo y temporada

### Paso 3 — IDs de torneos relevantes (Argentina)

| Torneo | unique_tournament_id | season_id |
|--------|---------------------|-----------|
| Liga Profesional de Fútbol (general) | 155 | varía por año |
| LPF Apertura 2026 | 155 | **87913** |
| Copa de la Liga 2025 | 13475 | **57487** |

Para encontrar el season_id de una temporada específica:
- Ir a `sofascore.com/tournament/football/argentina/{slug}/{unique_tournament_id}/season/{season_id}`
- O buscarlo en el JSON de un jugador que haya jugado esa temporada

### Paso 4 — Consolidar en archivo de stats del equipo

Guardar el archivo consolidado como `plantel_stats_{torneo}{año}.json` en la carpeta del club:
```json
{
  "season_id": 87913,
  "torneo": "LPF Apertura 2026",
  "fecha": "2026-04-25",
  "jugadores": [
    {
      "nombre": "Leandro Paredes",
      "sofascore_id": 123456,
      "pj": 13,
      "rating": 7.77,
      "goles": 2,
      "asistencias": 3
    }
  ]
}
```

### Consideraciones importantes

- **Rate limiting**: no correr múltiples scrapes en secuencia inmediata — esperar 10-20 segundos entre jugador y jugador.
- **GKs sin stats**: un GK puede no tener stats si fue suplente toda la temporada (ej: Brey en LPF 2026 mientras Marchesín era titular). Esto es correcto, no un error del scraper.
- **IDs dobles**: el scraper puede retornar `estadisticas_temporada: []` si usa el ID de la URL en vez del ID interno. Si pasa, buscar el ID interno en el `_raw.perfil.player.id`.
- **Fuente de ratings**: usar SofaScore primero. FotMob solo como fallback si SofaScore no tiene datos para ese torneo.

## Auditoría de contratos — proceso obligatorio en toda sesión de actualización

Cuando el usuario pida corregir, revisar o actualizar un dashboard ya existente, seguir este proceso **sin excepción** antes de tocar cualquier otra cosa:

### Paso 1 — Leer el PLANTEL array completo del dashboard

Identificar:
- Todos los jugadores con `c:"—"` (sin fecha de contrato)
- Cualquier fecha que parezca incongruente con la edad/trayectoria del jugador
- Jugadores sin campo `pr:` que deberían tenerlo (préstamos recibidos)
- Jugadores con `oc:` que podrían haber cambiado de monto

### Paso 2 — Consultar esta tabla de contratos verificados

Buscar el club en las tablas de abajo. Si el jugador aparece, usar esa fecha sin buscar de nuevo (ya fue verificada). Solo re-verificar si el dato tiene más de 3 meses de antigüedad o si hay novedades conocidas.

### Paso 3 — Buscar los que falten o sean dudosos

Para cada jugador sin fecha confirmada en la tabla:
```
WebSearch: "[nombre jugador] [club] contrato vencimiento [año actual]"
```
Fuentes válidas en orden de prioridad:
1. Transfermarkt (ficha oficial del jugador)
2. Sitio oficial del club
3. Prensa verificada: Infobae Deportes, ESPN, La Nación, TyC Sports, Olé, Doble Amarilla

### Paso 4 — Aplicar todas las correcciones al PLANTEL array

Hacer los cambios en batch (todos juntos), no de a uno. Luego auditar los KPIs y alertas que referencien jugadores por nombre o cuenten por grupo de vencimiento — esos también hay que actualizar.

### Paso 5 — Revisar KPIs y alertas que puedan haber quedado desactualizados

Buscar en el HTML hardcoded como:
- Conteos de jugadores: `"X jugadores"` en KPIs
- Listas de nombres: `"Jugador A · Jugador B · ..."`
- Totales de valor: `"€X.XM"`

Estos no se actualizan solos — hay que buscarlos y corregirlos manualmente después de cambiar el PLANTEL.

### Paso 6 — Actualizar la tabla de contratos verificados en este SKILL.md

Agregar o corregir las filas de la tabla correspondiente al club. Si se descubrió información nueva (lesión, clausula actualizada, interesados), agregarla en la columna Notas.

---

## Contratos verificados — Racing Club (abril 2026)

Fuente: Transfermarkt + prensa deportiva verificada (Racing de Alma, La Comu de Racing, ESPN, Infobae). Última verificación: 2026-04-26.

| Jugador | Contrato | Cláusula | Notas |
|---------|----------|----------|-------|
| Valentín Carboni | 31/12/2026 | — | Préstamo Inter Milan, sin OC. **LESIONADO** — LCA + colateral externo (27/2/2026). Operado. Baja 6-8 meses. No juega más en 2026. Milito gestionó con Inter en marzo. |
| Marcos Rojo | 30/06/2026 | — | No se renueva. Sale en junio. Fin de ciclo — 36 años. |
| Bruno Zuculini | 31/12/2026 | — | Racing planea extender a dic 2027. Sin firma aún (abr 2026). |
| Ezequiel Cannavo | 31/12/2026 | OC USD 2.5M (100%) | Préstamo Def. y Justicia. Titular indiscutido desde feb 2026. Ejercer OC urgente. |
| Damián Pizarro | 31/12/2026 | OC €5M (70%) | Préstamo Udinese. No conviene ejercer OC (al doble del VM). |
| Marco Di Césare | 31/12/2027 | USD 20M | Interés Roma y clubes de Brasil. Renovar con cláusula más alta antes de jun 2027. |
| Facundo Cambeses | 31/12/2027 | €12M | Renovación en negociación con mejora salarial. Cláusula sube en acuerdo proyectado. |
| Gastón Martirena | 31/12/2027 | €10M | Perdió titularidad ante Cannavo. Grêmio prepara oferta para julio 2026. Evaluar venta. |
| Baltasar Rodríguez | 31/12/2027 | €20M | Volvió del préstamo Inter Miami (no ejercieron OC $5M). |
| Nazareno Colombo | 31/12/2027 | — | Titular central. |
| Santiago Solari | 31/12/2027 | — | 28 años = ventana de venta activa. |
| Agustín García Basso | 31/12/2027 | — | 34 años, perdió titularidad. Quiere salir: San Lorenzo y Toluca interesados (jul 2026). |
| Tobías Rubio | 31/12/2027 | — | Lateral joven; se busca salida a préstamo para sumar minutos. |
| Francisco Gómez | 31/12/2027 | — | Portero suplente. |
| Gabriel Rojas | 31/12/2028 | USD 15M | Renovó jul 2025 (era dic 2026). Cláusula actualizada (era $10M). Mejor calificado LPF 2026. |
| Matías Zaracho | 31/12/2028 | — | |
| Adrián Martínez | 31/12/2028 | USD 122M | Cláusula más alta del fútbol argentino. Quiere retirarse en Racing. |
| Duván Vergara | 31/12/2028 | — | |
| Franco Pardo | 31/12/2028 | — | |
| Ignacio Rodríguez | 31/12/2028 | — | |
| Matías Tagliamonte | 31/12/2028 | — | Renovó dic 2025 (era dic 2026). Suplente de Cambeses. |
| Santiago Sosa | 31/12/2029 | €12M | Renovó a 2029. Conflicto salarial activo abr 2026. Monterrey tiene negociaciones avanzadas (~€12M). |
| Matko Miljevic | 31/12/2029 | — | |
| Tomás Conechny | 31/12/2029 | — | Fichado jul 2025 desde Alavés (~USD 3.5M, 100%). |
| Elías Torres | 31/12/2029 | — | |
| Alan Forneris | 31/12/2029 | — | Prospecto joven. |
| Adrián Fernández | 31/12/2029 | — | |
| Gonzalo Escudero | 31/12/2029 | — | |
| Tomás Pérez | — | — | Joven; Racing debe regularizar contrato. |

## Contratos verificados — Boca Juniors (abril 2026)

Fuente: Transfermarkt + prensa verificada (Infobae Deportes, ESPN, Olé, Doble Amarilla, Boca Juniors Oficial). Última verificación: 2026-04-26.

| Jugador | Contrato | Cláusula | Notas |
|---------|----------|----------|-------|
| Exequiel Zeballos | 31/12/2026 | USD 20M | Renovación estancada. Napoli interesado. Libre a negociar desde 1/7/2026. |
| Kevin Zenón | 31/12/2026 | — | Sin resolver. Boca rechazó €7M (Olympiacos) en ene 2025. Libre desde 1/7/2026. |
| Ander Herrera | 31/12/2026 | — | 36 años. Líder del vestuario. RENOVAR urgente — el plantel lo necesita en Libertadores. |
| Ángel Romero | 31/12/2026 | — | Llegó libre desde Corinthians ene 2026. Contrato + opción 1 año. Evaluar al cierre del Apertura. |
| Agustín Marchesín | 31/12/2026 | — | **LESIONADO** — rotura LCA rodilla derecha (abr 2026 Copa Lib). Operado. Baja ≥8 meses. Fin de ciclo, 38 años. |
| Edinson Cavani | 31/12/2026 | — | Renovó oct 2024. Declaró que se retira en Boca. 39 años, fin de ciclo. |
| Lucas Janson | 31/12/2027 | — | No en planes de Úbeda. Acordar salida para liberar masa salarial. |
| Milton Giménez | 31/12/2027 | — | |
| Malcom Braida | 31/12/2027 | — | |
| Marcelo Weigandt | 31/12/2027 | — | |
| Miguel Merentiel | 31/12/2027 | — | Renovó feb 2024. |
| Rodrigo Battaglia | 31/12/2027 | — | Llegó ene 2025. 34 años, pivote de experiencia europea. |
| Adam Bareiro | 31/12/2028 | — | |
| Leandro Paredes | 31/12/2028 | — | Capitán. Player of the Season Clausura 2025. |
| Ayrton Costa | 31/12/2028 | — | |
| Tomás Belmonte | 31/12/2028 | — | |
| Carlos Palacios | 31/12/2029 | — | Llegó ene 2025 desde Colo-Colo. |
| Juan Barinaga | 31/12/2028 | — | |
| Alan Velasco | 31/12/2028 | — | Llegó ene 2026. |
| Agustín Martegani | 31/12/2028 | — | No en planes de Úbeda. Buscar comprador. |
| Williams Alarcón | 31/12/2028 | — | Llegó ene 2025 (~€3.6M). Ciudadanía argentina en trámite desde feb 2026. |
| Marco Pellegrino | 30/06/2029 | — | |
| Santiago Ascacíbar | 31/12/2029 | — | Comprado ene 2026 (~USD 6M, 80% derechos). |
| Milton Delgado | 31/12/2029 | — | Joya de cantera. Renovó ene 2026. Interés europeo activo. |
| Lautaro Di Lollo | 31/12/2029 | USD 20M | Cláusula más alta del plantel (compartida con Zeballos y Aranda). |
| Lautaro Blanco | 31/12/2029 | — | |
| Tomás Aranda | 31/12/2029 | USD 20M | Era dic 2026, renovó a 2029. Debutó 28/1/2026. |
| Leandro Brey | 31/12/2029 | — | Nuevo titular tras lesión Marchesín. BLINDAR. |
| Gonzalo Gelini | 31/12/2030 | USD 10M | 19 años. Debutó titular 28/1/2026 (asistencia en debut). Joya en desarrollo. |
| Camilo Rey Domenech | 31/12/2029 | USD 20M | Boca le mejoró el contrato y decidió no prestarlo. Tendrá rodaje en 2026. |
| Javier García | 31/12/2026 | — | 39 años, tercer arquero. Renovó en ene 2026 por un año más. Último partido oficial: mar 2024. |

## Contratos verificados — Vélez Sársfield (abril 2026)

Fuente: Transfermarkt + prensa verificada (Infobae, ESPN, velez.com.ar, Doble Amarilla). Última verificación: 2026-04-26.

| Jugador | Contrato | Cláusula | Notas |
|---------|----------|----------|-------|
| Lucas Robertone | 31/12/2026 | ~€2.5M (obligatoria) | Préstamo UD Almería. Obligación de compra activa, se ejecuta verano 2026. |
| Matías Pellegrini | 31/12/2026 | — | Renovó dic 2025. Contrato + video de firma (filtró sueldo por error). |
| Rodrigo Piñeiro | 31/12/2026 | — | Llegó ene 2024 desde Unión Española (Chile). |
| Manuel Lanzini | 31/12/2026 | — | Llegó ago 2025 desde River (no convocado por Gallardo). |
| Imanol Machuca | 31/12/2026 | USD 2.5M (oblig.) | Préstamo Fortaleza EC. OC obligatoria si se cumplen objetivos (50% derechos). |
| Diego Valdés | 31/12/2027 | — | |
| Joaquín García | 31/12/2027 | — | |
| Aarón Quirós | 31/12/2027 | — | |
| Florián Monzón | 31/12/2027 | — | |
| Claudio Baeza | 31/12/2027 | — | |
| Lisandro Magallán | 31/12/2027 | — | |
| Braian Romero | 31/12/2027 | — | |
| Rodrigo Aliendro | 31/12/2027 | — | |
| Maximiliano Porcel | 31/12/2027 | — | |
| Álex Verón | 31/12/2027 | — | |
| Demián Domínguez | 31/12/2027 | — | |
| Leo Cristaldo | 31/12/2027 | — | |
| Álvaro Montero | 31/12/2027 | — | Comprado definitivamente mar 2026 (~USD 1M). Era préstamo Millonarios. |
| Tomás Marchiori | 31/12/2028 | — | |
| Emanuel Mammana | 31/12/2028 | — | |
| Elías Gómez | 31/12/2028 | — | |
| Jano Gordon | 31/12/2028 | — | |
| Thiago Silvero | 31/12/2028 | — | |
| Dilan Godoy | 31/12/2028 | — | |
| Álvaro Busso | 31/12/2028 | — | Primera firma oct 2025 (velez.com.ar). |
| Matías Arias | 31/12/2028 | — | |
| Tobías Andrada | 31/12/2029 | — | Mayor valor del plantel (€3M). 19 años. |

## What NOT to do

- Don't include scouting or tactical metrics (xG, heatmaps, pass maps). That's a different product for a different audience.
- Don't pad the dashboard with synthetic "demo" data to make it look fuller.
- Don't add a fourth area without user confirmation.
- Don't show unavailable data anywhere in the HTML — no "pendiente" tags, no empty cards, no placeholder charts. If it's not sourced, it doesn't exist in the dashboard.
- Don't use Power BI or any other tool that requires the user to assemble the output manually. The HTML is the final deliverable.
- Don't hardcode bar colors by array position in player charts — always derive from player data (see color rule above).

## When the user wants to iterate

If the user comes back saying "agregale X" or "cambiá Y", re-read the relevant reference file and adjust. Keep the three-area constraint unless they explicitly want to expand. If they ask for synthetic data or estimates, push back once and remind them of the real-data-only constraint — if they insist, document the deviation clearly in the README.

## Reference files

- `references/data_sources.md` — full list of reliable public sources per data type
- `references/data_model.md` — schema, relationships, DAX measures
- `references/visual_design.md` — layout, colors, chart choices, page-by-page spec
