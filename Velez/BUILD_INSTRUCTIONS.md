# Dashboard Vélez Sársfield — Instrucciones de Construcción en Power BI

**Tiempo estimado:** 45–60 minutos  
**Requisito:** Power BI Desktop (gratuito en microsoft.com/power-bi)

---

## Paso 0 — Completar datos pendientes ANTES de abrir Power BI

Antes de construir el modelo, completá los campos marcados en amarillo en los Excel:

### plantel.xlsx
Los campos `ValorMercadoEUR` y `FechaFinContrato` están en blanco.

1. Abrí: https://www.transfermarkt.es/ca-velez-sarsfield/kader/verein/1029
2. Para cada jugador, completá el valor de mercado en EUR y la fecha fin de contrato
3. También completá `MinutosTemporada` y `PartidosTemporada` desde SofaScore:
   https://www.sofascore.com/football/team/velez-sarsfield/3208

### finanzas.xlsx
Los campos de desglose (cuota societaria, derechos TV, sponsors, etc.) requieren leer el PDF del balance:

1. Descargá el balance desde: https://velez.com.ar/pdf/2024-balance-general.pdf
2. Completá las filas marcadas en amarillo con los valores del Estado de Recursos y Egresos

---

## Paso 1 — Crear el archivo Power BI

1. Abrí Power BI Desktop
2. Menú **View → Themes → Browse for themes**
3. Seleccioná el archivo `club-theme.json` de esta carpeta
4. Los colores azul marino y celeste de Vélez quedan aplicados en un clic

---

## Paso 2 — Importar los datos

1. **Home → Get Data → Excel Workbook**
2. Navegá a la carpeta `data/` e importá `plantel.xlsx`
   - Seleccioná la tabla **fact_Plantel** y la tabla **Transferencias_Recientes**
3. Repetí el proceso para `finanzas.xlsx`
   - Seleccioná **fact_Finanzas** y **fact_Deuda**
4. Repetí para `socios.xlsx`
   - Seleccioná **fact_Socios**

**Importante:** Filtrá las filas donde `FuenteConfirmada = "No"` si aún no las completaste. En Power Query: botón derecho en la columna → Filter → Does not equal → "No".

---

## Paso 3 — Construir la tabla de fechas (dim_Tiempo)

1. **Modeling → New Table**
2. Pegá esta fórmula DAX:

```dax
dim_Tiempo = 
ADDCOLUMNS(
    CALENDAR(DATE(2020,1,1), DATE(2026,12,31)),
    "Año", YEAR([Date]),
    "Mes", MONTH([Date]),
    "MesNombre", FORMAT([Date], "mmmm"),
    "Trimestre", "T" & FORMAT([Date], "Q"),
    "Temporada", FORMAT(YEAR([Date]), "0") & ""
)
```

---

## Paso 4 — Establecer relaciones

En la vista **Model** (ícono de diagrama), creá estas relaciones:

| Tabla origen | Campo | Tabla destino | Campo | Tipo |
|---|---|---|---|---|
| dim_Tiempo | Año | fact_Finanzas | EjercicioAño | 1:N (activa) |
| dim_Tiempo | Date | fact_Socios | Fecha | 1:N (activa) |
| dim_Tiempo | Date | fact_Plantel | FechaIngreso | 1:N (inactiva) |

La relación con `fact_Plantel` va por `FechaIngreso` pero los visuales filtrarán por `Temporada` directamente.

---

## Paso 5 — Crear las medidas DAX

**Home → New Measure** — pegá cada medida una por una:

### Plantel

```dax
ValorTotalPlantel = SUM(fact_Plantel[ValorMercadoEUR])

EdadPromedioPlantel = AVERAGE(fact_Plantel[Edad])

JugadoresEnPlantel = COUNTROWS(fact_Plantel)

JugadoresContratoVencer12M = 
CALCULATE(
    COUNTROWS(fact_Plantel),
    fact_Plantel[FechaFinContrato] <= TODAY() + 365
)

ValorMercadoPromedio = DIVIDE([ValorTotalPlantel], [JugadoresEnPlantel])
```

### Finanzas

```dax
IngresosTotales = 
CALCULATE(
    SUM(fact_Finanzas[MontoARS]),
    fact_Finanzas[Categoria] = "Ingreso"
)

EgresosTotales = 
CALCULATE(
    SUM(fact_Finanzas[MontoARS]),
    fact_Finanzas[Categoria] = "Egreso"
)

ResultadoEjercicio = [IngresosTotales] - [EgresosTotales]

MargenOperativo = DIVIDE([ResultadoEjercicio], [IngresosTotales])

ActivoTotal = 
CALCULATE(
    SUM(fact_Deuda[MontoUSD]),
    SEARCH("Activo Total", fact_Deuda[AcreedorTipo], 1, 0) > 0
)

PasivoTotal = 
CALCULATE(
    SUM(fact_Deuda[MontoUSD]),
    SEARCH("Pasivo Total", fact_Deuda[AcreedorTipo], 1, 0) > 0
)
```

### Socios

```dax
SociosTotales = 
CALCULATE(
    MAX(fact_Socios[CantidadSocios]),
    NOT(ISBLANK(fact_Socios[CantidadSocios]))
)

CuotaPlenaActual = 
CALCULATE(
    MAX(fact_Socios[CuotaPleno_ARS]),
    NOT(ISBLANK(fact_Socios[CuotaPleno_ARS]))
)

IngresoAnualPotencialSocios = [SociosTotales] * [CuotaPlenaActual] * 12

EvolucionCuotaPlena_YoY = 
VAR Actual = [CuotaPlenaActual]
VAR Anterior = CALCULATE(
    MAX(fact_Socios[CuotaPleno_ARS]),
    DATEADD(dim_Tiempo[Date], -1, YEAR)
)
RETURN DIVIDE(Actual - Anterior, Anterior)
```

---

## Paso 6 — Crear las 4 páginas del reporte

Tamaño de página en todas: **1280 × 720 px**  
(View → Page View → Actual Size; luego Format → Page → Custom → 1280 × 720)

---

### Página 1 — Resumen Ejecutivo

Layout: fila de 4 KPI cards arriba + 1 gráfico grande abajo.

**Visual 1 — KPI: Resultado del ejercicio**
- Card visual
- Valor: `ResultadoEjercicio`
- Formato condicional: verde si > 0, rojo si < 0
- Título: "Resultado del Ejercicio"
- Subtítulo: "En ARS — Ejercicio 115 (2024/25)"

**Visual 2 — KPI: Socios totales**
- Card visual
- Valor: `SociosTotales`
- Título: "Socios Registrados"
- Nota: usar el dato más reciente disponible

**Visual 3 — KPI: Valor del plantel**
- Card visual
- Valor: `ValorTotalPlantel`
- Formato: millones de EUR con sufijo "M€"
- Subtítulo: "Estimación Transfermarkt"

**Visual 4 — KPI: Posición en liga**
- Card visual con texto estático o tabla de 1 fila
- Texto: posición actual en LPF (completar manualmente)

**Visual 5 — Gráfico de barras: Ingresos vs Egresos histórico**
- Clustered bar chart (NO pie chart)
- Eje X: EjercicioAño (112, 114, 115)
- Eje Y: MontoARS (en billones)
- Leyenda: Categoria (Ingreso = azul Vélez, Egreso = rojo)

**Footer:** "Fuentes: Doble Amarilla, Transfermarkt, velez.com.ar | Actualizado: abr 2026"

---

### Página 2 — Plantel Deportivo

**Visual 1 — KPI: Valor total plantel** → `ValorTotalPlantel`  
**Visual 2 — KPI: Jugadores en plantel** → `JugadoresEnPlantel`  
**Visual 3 — KPI: Edad promedio** → `EdadPromedioPlantel`  
**Visual 4 — KPI: Contratos venciendo en 12 meses** → `JugadoresContratoVencer12M` (color naranja si > 5, rojo si > 10)  

**Visual 5 — Tabla: Top jugadores por valor**
- Campos: Jugador, Posicion, Edad, ValorMercadoEUR, FechaFinContrato
- Ordenar por ValorMercadoEUR DESC
- Conditional formatting en ValorMercadoEUR (escala azul)

**Visual 6 — Barras horizontales: Valor por posición**
- Eje Y: Posicion (Arquero, Defensor, Mediocampista, Delantero)
- Eje X: SUM(ValorMercadoEUR)
- Color: azul marino Vélez (#001D6E)

**Filtros:** slicer de Temporada (arriba derecha)

**Footer:** "Fuentes: velez.com.ar, Transfermarkt, ESPN | Estimaciones de valor: Transfermarkt"

---

### Página 3 — Finanzas Consolidadas

**Visual 1 — KPI: Ingresos totales** → `IngresosTotales`  
**Visual 2 — KPI: Egresos totales** → `EgresosTotales`  
**Visual 3 — KPI: Resultado** → `ResultadoEjercicio` (verde/rojo)  
**Visual 4 — KPI: Activo vs Pasivo (USD)**  
- Tarjeta doble: Activo $34.3M / Pasivo $44.5M (Ej 115)

**Visual 5 — Barras apiladas: Composición de ingresos** (completar cuando tengas el desglose del PDF)
- Eje X: EjercicioAño
- Apilado por Subcategoria
- Completar una vez cargado el desglose del balance

**Visual 6 — Gráfico de líneas: Evolución recursos ordinarios**
- Eje X: Ejercicio (112, 114, 115)
- Línea 1: Recursos Ordinarios Totales (verde)
- Línea 2: Egresos Ordinarios Totales (rojo)

**Filtro:** slicer de EjercicioAño

**Footer:** "Fuentes: Doble Amarilla (oct 2025), Diario Popular (oct 2022), velez.com.ar | Balance Ej 112, 114 y 115"

---

### Página 4 — Socios y Abonos

**Visual 1 — KPI: Socios registrados** → `SociosTotales`  
**Visual 2 — KPI: Cuota plena vigente** → `CuotaPlenaActual` (ARS/mes)  
**Visual 3 — KPI: Ingreso anual potencial** → `IngresoAnualPotencialSocios`  
**Visual 4 — KPI: Aumento de cuota YoY** → `EvolucionCuotaPlena_YoY` (%)

**Visual 5 — Gráfico de líneas: Evolución cuota plena**
- Eje X: Fecha (2023 → 2025)
- Eje Y: CuotaPleno_ARS
- Marcadores en cada actualización
- Anotar inflación de referencia si querés contexto

**Nota:** Los datos de socios por año solo tienen 2 puntos (2021: 33.225 y 2024: ~54.661). Para una línea más completa, completá los años intermedios desde los balances anuales (indicado en la hoja `Pendiente_Completar` de socios.xlsx).

**Footer:** "Fuentes: AFA ranking 2021 (Infobae), Wikipedia, velez.com.ar/socios/valores | Cuota: valores oficiales publicados"

---

## Paso 7 — Formato final

1. Agregá el logo de Vélez en el header de cada página (imagen PNG desde velez.com.ar)
2. Verificá que todos los números usen el formato correcto:
   - ARS en billones: `#,##0,, "B"` → muestra 71,9 B
   - ARS en millones: `#,##0, "M"` → muestra 1.200 M
   - EUR en millones: `#,##0, "M€"`
   - Porcentajes: `0.0%`
3. Asegurate de que el footer aparece en las 4 páginas
4. Guardá como `Velez_Dashboard_v1.pbix`

---

## Checklist final

- [ ] Theme aplicado (colores Vélez)
- [ ] 4 páginas con layout consistente
- [ ] KPI cards en la misma altura
- [ ] Footer con fuentes en todas las páginas
- [ ] Campos pendientes completados (Transfermarkt + PDF balance)
- [ ] Filtros de temporada/ejercicio funcionando
- [ ] Ningún visual vacío o con error
