# Visual Design — Layout, Colors, Page-by-Page Spec

This file defines the look and feel. Apply it consistently across all four pages.

## Filosofía visual

El dashboard es para un presidente o miembro de comisión directiva — gente que tiene 5 minutos para mirarlo, no 50. Cada página tiene que comunicar el estado del área en menos de 10 segundos. Si un visual requiere explicación, está mal diseñado.

**Reglas:**
1. Máximo 6 visuales por página (5 ideal)
2. Una sola métrica por KPI card
3. Títulos en español, sin jerga técnica
4. No usar pie charts (nunca, son ilegibles)
5. Colores con propósito (no decoración)
6. Espacios en blanco generosos

## Paleta de colores

El dashboard usa los colores institucionales del club, pero con un enfoque de "boardroom" (no fanático). Tres roles:

- **Color primario** — el principal del club (ej: azul Boca, rojo Independiente, celeste Racing)
- **Color secundario** — el complementario del club (ej: amarillo Boca, blanco)
- **Neutros** — gris oscuro para texto principal, gris medio para texto secundario, gris muy claro para fondos

Para semántica usar siempre los mismos colores independientes del club:
- **Verde** (#2E7D32) — métricas positivas, crecimiento, superávit
- **Rojo** (#C62828) — métricas negativas, déficit, alertas
- **Naranja** (#EF6C00) — atención, métricas en zona intermedia

### Theme JSON template

El skill produce un archivo `club-theme.json` que el usuario importa en Power BI (View → Themes → Browse for themes). Estructura genérica:

```json
{
  "name": "Club Executive Theme",
  "dataColors": [
    "#1A237E",
    "#FFC107",
    "#2E7D32",
    "#C62828",
    "#EF6C00",
    "#546E7A",
    "#90A4AE",
    "#CFD8DC"
  ],
  "background": "#FFFFFF",
  "foreground": "#212121",
  "tableAccent": "#1A237E",
  "textClasses": {
    "title": {
      "fontFace": "Segoe UI Semibold",
      "fontSize": 16,
      "color": "#212121"
    },
    "header": {
      "fontFace": "Segoe UI",
      "fontSize": 12,
      "color": "#424242"
    },
    "label": {
      "fontFace": "Segoe UI",
      "fontSize": 10,
      "color": "#616161"
    }
  }
}
```

Ajustar los dos primeros colores a los del club.

## Logo del club

Usar siempre el logo oficial del club en el header, arriba a la derecha. La fuente es la CDN de Transfermarkt:

```
https://tmssl.akamaized.net/images/wappen/big/{TRANSFERMARKT_ID}.png
```

IDs confirmados: Vélez=1029, Racing=1444, River=997, Boca=998, Independiente=50, San Lorenzo=1026.

**Implementación en el header HTML:**
```html
<header>
  <div style="flex:1">
    <h1>Club Atlético Vélez Sársfield — Dashboard Ejecutivo</h1>
    <p>Temporada 2025/26 · Fuentes · Fecha</p>
  </div>
  <img src="https://tmssl.akamaized.net/images/wappen/big/1029.png"
       alt="Nombre Club"
       style="height:64px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.4));flex-shrink:0">
</header>
```

El header debe tener `display:flex; align-items:center; gap:16px` para que el logo quede alineado a la derecha del texto.
Aplicar el mismo logo e implementación en `informe.html`.

## Tipografía

- **Títulos de página y visuales:** Segoe UI Semibold 14-16pt
- **KPI cards (número grande):** Segoe UI Bold 28-36pt
- **Etiquetas y ejes:** Segoe UI 10pt
- **No usar Calibri ni fuentes con serifa**

## Layout estándar de cada página

```
┌──────────────────────────────────────────────────────┐
│ HEADER: Logo club + Nombre página + Filtro temporada │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                    │
│  │ KPI │ │ KPI │ │ KPI │ │ KPI │   (4 KPI cards)   │
│  └─────┘ └─────┘ └─────┘ └─────┘                    │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────┐         │
│  │                  │  │                  │         │
│  │  Visual grande   │  │  Visual grande   │         │
│  │   (gráfico)      │  │   (tabla/gráf)   │         │
│  │                  │  │                  │         │
│  └──────────────────┘  └──────────────────┘         │
│                                                      │
│ FOOTER: Fuentes y fecha de actualización             │
└──────────────────────────────────────────────────────┘
```

Tamaño recomendado de página: 1280x720 px (16:9, óptimo para presentar en pantalla).

## Página 1 — Resumen Ejecutivo

**Propósito:** snapshot que el presidente puede ver en 30 segundos para saber cómo está el club.

**Visuales (5):**

1. **KPI grande arriba a la izquierda — Resultado del último ejercicio**
   - Número grande con signo (ARS millones)
   - Color verde si positivo, rojo si negativo
   - Subtítulo: "Ejercicio [año]"

2. **KPI — Cantidad de socios**
   - Número grande
   - Variación YoY como subtítulo (ej: "+3.2% vs año anterior")

3. **KPI — Valor de mercado del plantel**
   - En millones de EUR
   - Subtítulo: "Estimación Transfermarkt"

4. **KPI — Resultado deportivo de la temporada**
   - Posición en liga + último resultado relevante (campeón, copa, descenso evitado, etc.)
   - Texto, no número

5. **Gráfico de barras grande abajo — Evolución de ingresos vs egresos últimos 5 años**
   - Doble barra apilada o doble línea
   - Eje Y: ARS millones
   - Eje X: años

**No incluir** filtros interactivos en esta página — es vista de lectura, no de exploración.

## Página 2 — Plantel Deportivo

**Propósito:** entender el activo más caro del club: los jugadores.

**Visuales (5-6):**

1. **KPI — Valor total del plantel** (EUR millones)
2. **KPI — Cantidad de jugadores en plantel**
3. **KPI — Edad promedio**
4. **KPI — Jugadores con contrato venciendo en próximos 12 meses** (alerta de riesgo)
5. **Tabla — Top 15 jugadores por valor de mercado**
   - Columnas: Jugador, Posición, Edad, Valor (EUR), Contrato hasta, Minutos
   - Conditional formatting en columna Valor (escala de color)
6. **Gráfico de barras horizontales — Distribución del valor por posición**
   - Suma del valor por posición (Arquero, Defensores, Volantes, Delanteros)

**Filtros laterales:** temporada, posición.

## Página 3 — Finanzas Consolidadas

**Propósito:** entender la salud financiera del club.

**Visuales (6):**

1. **KPI — Ingresos totales** (último ejercicio)
2. **KPI — Egresos totales**
3. **KPI — Resultado del ejercicio** (verde/rojo según signo)
4. **KPI — Margen operativo** (%)
5. **Gráfico de barras apiladas — Composición de ingresos por categoría** (último año)
   - Cuota societaria, derechos TV, sponsors, transferencias, taquilla, otros
6. **Gráfico de líneas — Evolución de ingresos y egresos últimos 5 años**
   - Dos líneas (ingresos verde, egresos rojo)
   - Si hay datos, línea adicional con resultado neto

**Filtros laterales:** ejercicio.

**Si hay datos de deuda**, agregar visual extra a la derecha con composición de deuda.

## Página 4 — Socios y Abonos

**Propósito:** entender la base de socios — el activo más estratégico de un club argentino.

**Visuales (5):**

1. **KPI — Socios totales actuales**
2. **KPI — Variación YoY** (%)
3. **KPI — Cuota promedio** (ARS)
4. **KPI — Ingreso anual potencial por cuotas** (ARS millones)
5. **Gráfico de líneas grande — Evolución de cantidad de socios últimos 5-10 años**
   - Eje Y: cantidad
   - Eje X: año
   - Anotar eventos importantes (descenso, campeonato, cambio de presidencia) si está claro

**Si hay desglose por categoría**, agregar gráfico de barras horizontales con cantidad por categoría.

## Footer (todas las páginas)

Texto chico abajo:
> "Fuentes: [lista]. Última actualización: [fecha]. Datos públicos verificables."

Esto es CRÍTICO — la credibilidad del dashboard depende de que se vean las fuentes.

## Checklist final antes de entregar

- [ ] Las 4 páginas tienen el mismo layout y tipografía
- [ ] El theme está aplicado (colores consistentes)
- [ ] Cada visual tiene título claro
- [ ] Los números tienen formato (millones con sufijo M, miles con K, decimales reducidos)
- [ ] Los KPI cards tienen la misma altura
- [ ] No hay visuales vacíos o "Coming soon"
- [ ] El footer con fuentes está en todas las páginas
- [ ] El archivo .pbix abre sin errores
- [ ] Los datos del modelo coinciden con las fuentes documentadas
