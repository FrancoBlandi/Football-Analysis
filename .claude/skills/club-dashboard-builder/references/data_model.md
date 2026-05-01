# Data Model — Schema, Relationships, DAX

This file defines the data model the dashboard must use. The user replicates this in Power BI Desktop following BUILD_INSTRUCTIONS.md.

## Star schema overview

The model uses a star schema with one date dimension and three fact tables (one per area). This is the simplest possible structure — keep it that way unless the data really requires more complexity.

```
                    dim_Tiempo
                        |
        ┌───────────────┼───────────────┐
        |               |               |
   fact_Plantel    fact_Finanzas   fact_Socios
```

## Tables

### dim_Tiempo (date dimension)

| Column | Type | Notes |
|---|---|---|
| Fecha | Date | Primary key, daily granularity |
| Año | Integer | YEAR(Fecha) |
| Mes | Integer | MONTH(Fecha) |
| MesNombre | Text | "Enero", "Febrero", etc. |
| Trimestre | Text | "T1", "T2", etc. |
| Temporada | Text | "2024", "2024/25" depending on club's fiscal year |

**How to build in Power BI:**
```dax
dim_Tiempo = 
ADDCOLUMNS(
    CALENDAR(DATE(2015,1,1), DATE(2025,12,31)),
    "Año", YEAR([Date]),
    "Mes", MONTH([Date]),
    "MesNombre", FORMAT([Date], "mmmm"),
    "Trimestre", "T" & FORMAT([Date], "Q"),
    "Temporada", YEAR([Date]) & ""
)
```

### fact_Plantel (snapshot por temporada)

| Column | Type | Source |
|---|---|---|
| Temporada | Text | Manual |
| Jugador | Text | Transfermarkt |
| Posicion | Text | Transfermarkt |
| Edad | Integer | Transfermarkt |
| FechaIngreso | Date | Transfermarkt |
| FechaFinContrato | Date | Transfermarkt |
| ValorMercadoEUR | Currency | Transfermarkt |
| CostoFichajeEUR | Currency | Transfermarkt (cuando hay) |
| TipoIncorporacion | Text | "Compra", "Préstamo", "Libre", "Cantera" |
| MinutosTemporada | Integer | SofaScore/Transfermarkt |
| PartidosTemporada | Integer | Transfermarkt |
| Goles | Integer | Transfermarkt |
| Asistencias | Integer | Transfermarkt |

**Granularidad:** una fila por jugador por temporada. Si el plantel actual tiene 30 jugadores y querés cubrir 5 temporadas, son ~150 filas.

### fact_Finanzas (anual o por ejercicio)

Modelo de líneas (long format), no de columnas:

| Column | Type | Source |
|---|---|---|
| EjercicioAño | Integer | Balance |
| Categoria | Text | "Ingreso" o "Egreso" |
| Subcategoria | Text | "Cuota societaria", "Derechos TV", "Salarios", etc. |
| MontoARS | Currency | Balance |
| FechaCierre | Date | Balance |

**Por qué long format:** facilita los visuales, evita explotar columnas, y permite agregar nuevas subcategorías sin romper el modelo.

**Tabla complementaria recomendada:** `fact_Deuda` con la composición de deuda por año si está disponible.

### fact_Socios

| Column | Type | Source |
|---|---|---|
| Fecha | Date | Memoria anual o publicación |
| CantidadSocios | Integer | Sitio oficial / memoria |
| Categoria | Text | "Activo", "Vitalicio", "Cadete", etc. (si se desglosa) |
| CuotaMensualARS | Currency | Sitio oficial |

**Granularidad:** la mejor que tenga el club. Si solo hay datos anuales, una fila por año por categoría. Si hay mensuales, mensual.

## Relaciones

- `dim_Tiempo[Fecha]` → `fact_Plantel[FechaIngreso]` (1:N, no activa por default)
- `dim_Tiempo[Año]` → `fact_Finanzas[EjercicioAño]` (1:N, activa)
- `dim_Tiempo[Fecha]` → `fact_Socios[Fecha]` (1:N, activa)

Para `fact_Plantel`, la relación con tiempo es por `FechaIngreso` pero la mayoría de visuales filtra por `Temporada` directamente, no por relación.

## Medidas DAX core (must-have)

### Plantel

```dax
ValorTotalPlantel = SUM(fact_Plantel[ValorMercadoEUR])

CostoTotalIncorporaciones = 
CALCULATE(
    SUM(fact_Plantel[CostoFichajeEUR]),
    fact_Plantel[TipoIncorporacion] = "Compra"
)

EdadPromedioPlantel = AVERAGE(fact_Plantel[Edad])

JugadoresEnPlantel = COUNTROWS(fact_Plantel)

JugadoresContratoVencer12M = 
CALCULATE(
    COUNTROWS(fact_Plantel),
    fact_Plantel[FechaFinContrato] <= TODAY() + 365
)

ValorMercadoPromedio = DIVIDE([ValorTotalPlantel], [JugadoresEnPlantel])

MinutosPromedio = AVERAGE(fact_Plantel[MinutosTemporada])
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

IngresosCuotaSocios = 
CALCULATE(
    SUM(fact_Finanzas[MontoARS]),
    fact_Finanzas[Subcategoria] = "Cuota societaria"
)

ParticipacionCuotaSocios = DIVIDE([IngresosCuotaSocios], [IngresosTotales])

CostoSalarial = 
CALCULATE(
    SUM(fact_Finanzas[MontoARS]),
    fact_Finanzas[Subcategoria] = "Salarios"
)

PesoSalariosSobreIngresos = DIVIDE([CostoSalarial], [IngresosTotales])
```

### Socios

```dax
SociosTotales = 
CALCULATE(
    SUM(fact_Socios[CantidadSocios]),
    LASTDATE(fact_Socios[Fecha])
)

VariacionSociosVsAnioAnterior = 
VAR Actual = [SociosTotales]
VAR Anterior = CALCULATE([SociosTotales], DATEADD(dim_Tiempo[Fecha], -1, YEAR))
RETURN DIVIDE(Actual - Anterior, Anterior)

CuotaPromedioActual = 
CALCULATE(
    AVERAGE(fact_Socios[CuotaMensualARS]),
    LASTDATE(fact_Socios[Fecha])
)

IngresoMensualPotencialSocios = [SociosTotales] * [CuotaPromedioActual]

IngresoAnualPotencialSocios = [IngresoMensualPotencialSocios] * 12
```

## Medidas opcionales (nice-to-have)

```dax
// Si hay datos de varios años de plantel
EvolucionValorPlantel_YoY = 
VAR Actual = [ValorTotalPlantel]
VAR Anterior = CALCULATE([ValorTotalPlantel], DATEADD(dim_Tiempo[Fecha], -1, YEAR))
RETURN DIVIDE(Actual - Anterior, Anterior)

// Cobertura de cuota societaria sobre salarios
CoberturaSociosSobreSalarios = DIVIDE([IngresoAnualPotencialSocios], [CostoSalarial])
```

## Reglas de oro del modelo

1. **Una sola tabla de fechas.** Nunca crear dim_Tiempo por área.
2. **Long format en finanzas.** No tabla pivoteada con columnas por categoría.
3. **No hardcodear valores.** Si necesitás un parámetro (ej: tipo de cambio), creá una tabla de parámetros.
4. **Documentar cada medida.** Usar el campo descripción en Power BI para que cualquiera entienda qué calcula.
