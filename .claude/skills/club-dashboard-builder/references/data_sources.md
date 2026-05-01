# Data Sources — Argentine Football Clubs

This file lists every public data source the skill can use, organized by area. **If a metric isn't here, it can't be sourced reliably and must be excluded from the dashboard.**

## Plantel Deportivo

### Plantel actual e histórico
- **Source:** Transfermarkt — `https://www.transfermarkt.es/[club-slug]/startseite/verein/[id]`
- **Fields available:** nombre del jugador, edad, posición, fecha de nacimiento, fecha de contrato, fin de contrato, valor de mercado, club anterior, costo de fichaje
- **How to fetch:** web_fetch the squad page. For historical seasons, use `/saison_id/[year]` suffix
- **Reliability:** ⭐⭐⭐⭐⭐ — most reliable single source for plantel data
- **Caveat:** valor de mercado es estimación de Transfermarkt, no precio real de venta. Es una métrica aceptada por la industria pero hay que mostrarla como tal.

### Operaciones de mercado (compras/ventas)
- **Source 1:** Transfermarkt → "Ficha del club" → "Transferencias"
- **Source 2:** Sitio oficial del club (sección noticias o prensa)
- **Source 3:** Diarios deportivos: Olé, La Nación deportes, TyC Sports, Doble Amarilla
- **Fields available:** jugador, fecha, club origen/destino, monto (cuando se publica), tipo (compra, préstamo, venta, libre)
- **Reliability:** ⭐⭐⭐⭐ — los montos no siempre se publican; cuando faltan, marcar "no informado"

### Salarios de jugadores
- **NO HAY FUENTE PÚBLICA CONFIABLE.** Los salarios reales son confidenciales.
- **Excluir esta métrica del dashboard** salvo que el club haya publicado el dato (algunos balances incluyen "masa salarial total" pero no por jugador).
- Si el usuario insiste, usar la masa salarial agregada del balance anual y dividirla en proporción al valor de mercado como aproximación documentada — **pero esto viola el constraint de "datos reales"**, así que mejor evitar.

### Minutos jugados, partidos, rendimiento básico
- **Source 1:** Transfermarkt → "Estadísticas del jugador"
- **Source 2:** SofaScore — `https://www.sofascore.com/`
- **Source 3:** ESPN deportes
- **Fields available:** partidos jugados, minutos, goles, asistencias, tarjetas
- **Reliability:** ⭐⭐⭐⭐⭐

## Finanzas Consolidadas

### Estados contables anuales
- **Source 1:** Sitio oficial del club, sección "Institucional" o "Memoria y Balance"
  - Boca: https://www.bocajuniors.com.ar/club/balance
  - River: https://www.cariverplate.com.ar/institucional/memoria-balance
  - Racing: balance presentado en asamblea anual, suele estar en la sección institucional
  - Vélez, San Lorenzo, Independiente, Lanús, etc.: variable, buscar "memoria y balance [club] [año]"
- **Source 2:** Prensa especializada que cubre asambleas anuales (La Nación, Clarín, Doble Amarilla)
- **Fields disponibles:** ingresos totales, egresos totales, resultado del ejercicio, activo, pasivo, patrimonio neto, deuda, masa salarial total
- **Reliability:** ⭐⭐⭐⭐ — los grandes publican, los chicos no siempre

### Desglose de ingresos
Los balances suelen romper ingresos en categorías. Las más comunes:
- Cuota societaria
- Derechos de TV (de la liga, vía AFA/LPF)
- Sponsors y publicidad
- Venta de jugadores (transferencias)
- Recaudación de partidos (taquilla)
- Otros (merchandising, alquileres, etc.)

### Desglose de egresos
- Salarios (cuerpo técnico + plantel + empleados)
- Gastos operativos
- Premios y bonus
- Servicios (luz, agua, mantenimiento)
- Amortizaciones de pases

### Deuda
- Deuda total y composición (bancaria, comercial, FIFA, AFIP) — aparece en el balance
- A veces se publica deuda con jugadores y representantes

## Socios y Abonos

### Cantidad de socios totales
- **Source 1:** Sitio oficial del club (algunos publican el número en la home)
- **Source 2:** Memoria anual (campo "evolución de masa societaria")
- **Source 3:** Ranking AFA de socios (publicación periódica)
- **Source 4:** Wikipedia del club — suele tener cantidad actualizada de socios
- **Reliability:** ⭐⭐⭐⭐ para totales anuales, ⭐⭐ para datos mensuales

### Cuota societaria
- **Source 1:** Sitio oficial del club, sección "Hacete socio" o "Categorías de socios"
- **Reliability:** ⭐⭐⭐⭐⭐ para el valor actual; histórico de aumentos requiere archivar capturas o buscar en Wayback Machine

### Categorías de socios
- Cada club tiene su esquema. Boca tiene Activo, Vitalicio, Adherente, etc. Lo que se publique varía.
- **Source:** sitio oficial del club

### Abonos a partidos (no es lo mismo que socios)
- **Source 1:** Sitio oficial del club
- **Source 2:** Prensa cuando se anuncia una nueva campaña de abonos
- **Fields:** precio del abono por categoría (popular, platea, palco), cantidad vendida (pocas veces se publica)

### Datos NO disponibles públicamente (excluir)
- Altas y bajas de socios mensual
- Cohortes de retención
- Demografía detallada de socios
- LTV por categoría
- Pagos atrasados o morosidad
- Detalle de abonos vendidos por sector

## Resultados deportivos (cross-cutting, útil en varias páginas)

- **Source:** SofaScore, ESPN, Transfermarkt, sitio oficial
- **Fields:** posición en liga, puntos, partidos ganados/empatados/perdidos, goles a favor/en contra, racha, copas internacionales

## Cómo registrar fuentes en los Excel

Cada archivo .xlsx debe tener una hoja `Sources` con esta estructura:

| Métrica | Fuente | URL | Fecha de extracción | Notas |
|---|---|---|---|---|
| Cantidad de socios 2024 | Sitio oficial Vélez | https://velez.com.ar/... | 2025-04-19 | Dato a diciembre 2024 |
| Valor de mercado plantel | Transfermarkt | https://www.transfermarkt... | 2025-04-19 | Estimación TM |

Esto es crítico: el usuario debe poder auditar cualquier número.

## Clubes con más data pública disponible (ranking aproximado)

1. **Boca y River** — los que más publican, mejor estructurado
2. **Racing, San Lorenzo, Independiente** — publican balance, datos sueltos
3. **Vélez, Estudiantes, Lanús, Newell's, Rosario Central** — publican balance pero menos detalle
4. **Resto de Primera** — variable, hay que rebuscar

Si el club elegido tiene poca data pública, el dashboard va a quedar más chico — eso es honesto y aceptable. Mejor un dashboard con 20 métricas reales que 50 inventadas.
