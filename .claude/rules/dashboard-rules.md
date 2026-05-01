# Reglas del Dashboard — Siempre aplicar

## Datos

**SOLO DATOS REALES Y VERIFICABLES.**

- Cada número en el dashboard debe tener una fuente pública documentada
- NUNCA inventar, estimar, aproximar o simular datos sin decírselo explícitamente al usuario
- NUNCA usar frases como "dato estimado", "aproximado" o "simulado" para justificar datos fabricados — si no existe el dato, el campo no va en el dashboard
- Si una métrica no está disponible públicamente para el club elegido, se excluye sin reemplazo
- Fuentes aceptadas: balances oficiales del club, Transfermarkt, SofaScore, sitio oficial del club, prensa deportiva verificable (Olé, La Nación, TyC Sports, Doble Amarilla, Infobae Deportes)
- NUNCA usar Wikipedia como fuente de datos — es editable y no tiene respaldo oficial
- NUNCA usar foros, redes sociales o fuentes anónimas como dato primario
- Cada archivo Excel debe tener una hoja `Sources` con URL, fecha de extracción y notas por cada métrica

## Alcance

- Tres áreas únicamente: Plantel Deportivo, Finanzas Consolidadas, Socios y Abonos
- NO agregar áreas sin confirmación explícita del usuario
- NO incluir métricas de scouting o análisis táctico (xG, heatmaps, pass maps, etc.)
- La audiencia es la dirigencia del club — los visuales deben ser legibles en 5 segundos

## Diseño

- Máximo 6 visuales por página (5 ideal)
- NO usar pie charts
- Títulos en español, sin jerga técnica
- Footer con fuentes en todas las páginas
- Tamaño de página: 1280x720 px

## Output

- El output es un archivo `dashboard.html` que abre directo en el browser — no Power BI, no herramientas externas
- Los datos no disponibles NO aparecen en el dashboard en ninguna forma (ni como placeholder, ni como "pendiente", ni como campo vacío)
- Documentar en README qué métricas se incluyeron y cuáles se excluyeron por falta de datos públicos
