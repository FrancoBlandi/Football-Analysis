# Dashboard Ejecutivo — Club Atlético Vélez Sársfield

Paquete de construcción para Power BI. Generado el 19 de abril de 2026.

## Contenido

```
Velez/
├── data/
│   ├── plantel.xlsx        — Plantel 2025/26 + transferencias recientes
│   ├── finanzas.xlsx       — Balances Ej 112, 114 y 115 (+ estructura para desglose)
│   └── socios.xlsx         — Evolución cuotas 2023-2025 + socios disponibles
├── club-theme.json         — Paleta Vélez para importar en Power BI (1 clic)
├── BUILD_INSTRUCTIONS.md   — Guía paso a paso para armar el .pbix
└── README.md               — Este archivo
```

## Métricas incluidas (con fuente verificada)

### Plantel Deportivo
| Métrica | Fuente | Estado |
|---|---|---|
| Lista de jugadores 2025/26 (31 jugadores) | velez.com.ar + ESPN | ✓ Completo |
| Posición, edad, nacionalidad | velez.com.ar + ESPN | ✓ Completo |
| Tipo de incorporación (libre/compra/cantera) | BeSoccer + prensa | ✓ Completo |
| Transferencia Maher Carrizo a Ajax (€7M) | Doble Amarilla / El Intransigente | ✓ Completo |
| Valor de mercado individual (EUR) | Transfermarkt | ⚠ PENDIENTE |
| Fecha fin de contrato | Transfermarkt | ⚠ PENDIENTE |
| Minutos / partidos por jugador | Transfermarkt / SofaScore | ⚠ PENDIENTE |

### Finanzas Consolidadas
| Métrica | Fuente | Estado |
|---|---|---|
| Resultado Ej 115 (2024/25): Superávit > USD 25M | Doble Amarilla | ✓ Completo |
| Recursos ordinarios Ej 114 y 115 (ARS) | Doble Amarilla | ✓ Completo |
| Egresos ordinarios Ej 114 y 115 (ARS) | Doble Amarilla | ✓ Completo |
| Déficit Ej 114 (2023/24): ARS -1.551.939.880 | Doble Amarilla | ✓ Completo |
| Superávit Ej 112 (2021/22): ARS 1.200.000.000 | Diario Popular | ✓ Completo |
| Activo total Ej 114 y 115 (USD) | Doble Amarilla | ✓ Completo |
| Pasivo total Ej 114 y 115 (USD) | Doble Amarilla | ✓ Completo |
| Deuda Botafogo por Montoro: > USD 3M | Doble Amarilla | ✓ Completo |
| Desglose ingresos por categoría (cuotas, TV, etc.) | Balance PDF | ⚠ PENDIENTE |
| Masa salarial (total) | Balance PDF | ⚠ PENDIENTE |
| Deuda por composición (bancaria/AFIP/FIFA) | Balance PDF | ⚠ PENDIENTE |
| Resultado Ej 113 (2022/23) | Balance PDF | ⚠ PENDIENTE |

### Socios y Abonos
| Métrica | Fuente | Estado |
|---|---|---|
| Socios 2021: 33.225 (AFA ranking, posición 10) | Infobae / AFA | ✓ Completo |
| Socios ~54.661 (dato reciente, Wikipedia) | Wikipedia | ✓ Completo |
| Cuota plena: historial 2023–2025 (6 puntos) | velez.com.ar | ✓ Completo |
| Cuota semiplena H y M: historial 2023–2025 | velez.com.ar | ✓ Completo |
| Cuota cadete e infantil 2025 | velez.com.ar | ✓ Completo |
| Socios por año 2022, 2023, 2024 (exactos) | Balance anual PDF | ⚠ PENDIENTE |
| Desglose socios por categoría | Balance anual | ⚠ PENDIENTE |
| Cantidad de abonos vendidos | Prensa (no siempre publicado) | ⚠ NO DISPONIBLE |

## Métricas excluidas (no disponibles públicamente)

- **Salarios individuales de jugadores** — Son confidenciales. El balance solo publica la masa salarial total. Excluido por regla de datos reales.
- **Detalle de abonos por sector (popular, platea, palco)** — Vélez no publica la cantidad vendida por sector.
- **Morosidad / retención de socios** — No hay fuente pública.
- **Demografía de socios** — No publicada.
- **Ingresos por merchandising (separado)** — Incluido en "Otros" en el balance, no desagregado.

## Cómo completar los pendientes

1. **Transfermarkt:** ir a https://www.transfermarkt.es/ca-velez-sarsfield/kader/verein/1029 y completar columnas de plantel.xlsx marcadas en amarillo.
2. **Balance PDF:** descargar https://velez.com.ar/pdf/2024-balance-general.pdf y completar las filas en amarillo de finanzas.xlsx.
3. **Socios por año:** ir a https://velez.com.ar/elclubesdelossocios/memorias-estados-contables y revisar los PDF de ejercicios 112–115.

## Notas sobre los datos financieros

Los balances de Vélez cierran el **30 de junio** de cada año (no diciembre).

- **Ejercicio 112:** 1 jul 2021 – 30 jun 2022
- **Ejercicio 113:** 1 jul 2022 – 30 jun 2023
- **Ejercicio 114:** 1 jul 2023 – 30 jun 2024
- **Ejercicio 115:** 1 jul 2024 – 30 jun 2025

El superávit del Ejercicio 115 (>USD 25M) contrasta con los recursos ordinarios menores a los egresos ordinarios, lo que indica que el resultado positivo proviene principalmente de **ingresos extraordinarios** (probable venta parcial de Maher Carrizo a Ajax, pagos pendientes de Botafogo, y otras operaciones de pases). Esto debe quedar claro en el dashboard con una nota contextual.
