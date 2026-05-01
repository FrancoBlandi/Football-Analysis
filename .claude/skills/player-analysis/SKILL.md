# Skill: Análisis Ejecutivo de Jugador

## Cuándo usar este skill
Cuando el usuario pide evaluar si conviene vender, retener o reemplazar un jugador clave. El output es una sección HTML lista para insertar en un informe ejecutivo (`analisis_[jugador].html`).

---

## Proceso paso a paso

### 1. Perfil táctico del jugador
- Identificar las posiciones reales que ocupa (no solo la nominal)
- Detectar si cubre múltiples roles en distintos sistemas (ej: pivot 4-3-3 Y líbero 3-4-3)
- Fuentes: SofaScore (posiciones registradas), prensa táctica (El Primer Grande, Racing de Alma)
- **Regla**: si el jugador cubre 2 roles diferentes, eso es el argumento central del análisis

### 2. Situación contractual y mercado
- Valor de mercado actual (Transfermarkt)
- Fecha de vencimiento de contrato
- Existencia de cláusula de rescisión y quién la activa (**siempre un club comprador**, nunca el club vendedor)
- Conflictos activos: salariales, oferta de agente, declaraciones públicas del jugador
- Fuentes: Transfermarkt, Racing de Alma, Bolavip, prensa verificable
- **Regla**: no usar Wikipedia, foros ni redes sociales como fuente primaria

### 3. Buscar reemplazos realistas
- Filtrar por: mismo mercado (Argentina/Uruguay/región), rango de valor ≤ ingreso esperado por venta, experiencia comprobada en los roles identificados en el paso 1
- **Regla crítica**: solo incluir jugadores que sean transferencias realistas para el club en cuestión (no estrellas de grandes, no jugadores que ya rechazaron el club)
- Si un jugador cubre los 2 roles → es directo comparable
- Si ningún jugador individual cubre los 2 roles → presentar la combinación mínima de 2 jugadores necesarios
- Fuentes: Transfermarkt, SofaScore, prensa deportiva

### 4. Comparativa estadística
- Métricas por 90 min (no totales): duelos ganados, intercepciones, tackles, precisión de pase, rating
- Comparar solo con el reemplazo ya en el club o el más cercano disponible
- Si los datos del comparable son de muestra pequeña (ej: 1 partido), indicarlo explícitamente
- Destacar la brecha más significativa — ese es el número que la dirigencia necesita
- Fuentes: SofaScore, Alargue, Flashscore

### 5. Escenarios de decisión
Presentar siempre **3 escenarios** con nombre claro:
1. **Retención** — costo de renovar, riesgo de perderlo gratis, beneficio táctico
2. **Venta con reemplazo** — ingreso neto real (precio − costo de reemplazos), degradación táctica cuantificada
3. **Salida sin reemplazo** — solo si es viable; si no, decirlo explícitamente

### 6. Veredicto ejecutivo
- Una recomendación clara (retener / vender con condiciones / dejar salir)
- Máximo 3 bullets de sustento
- Highlight del número más importante para la reunión

---

## Reglas de contenido

- **Solo datos verificables** — si no hay fuente pública, el dato no va
- **No mencionar clubes específicos** como destino potencial a menos que haya confirmación periodística verificable
- Usar lenguaje de dirigencia, no de scouting (no xG, no heatmaps, no pass maps)
- Fuentes de River Plate o medios con conflicto de interés evidente: excluir del informe
- Cualquier dato estimado o con muestra pequeña: indicarlo en nota al pie

---

## Estructura HTML del output

```
[Sección: Doble rol — qué hace que sea difícil de reemplazar]
  → card con tags de rol (SI / NO / PARCIAL) para cada candidato
  → canvas ch-roles: grouped bar chart pivot vs líbero (escala 1–5)

[Sección: Conflicto contractual]
  → alert.r si hay conflicto activo
  → KPIs: valor, cláusula, vencimiento, sueldo estimado

[Sección: Comparativa estadística]
  → barras horizontales: jugador vs comparable, métricas por 90
  → nota de muestra si aplica

[Sección: Dos jugadores para reemplazar uno]
  → tabla comparativa: roles, costo, disponibilidad
  → cálculo neto explícito

[Sección: Tres escenarios]
  → cards con nombre, descripción, riesgo, costo/ingreso neto

[Sección: Recomendación ejecutiva]
  → veredicto bold, bullets de sustento, número clave destacado
```

---

## Colores y variables CSS reutilizables

```js
const AZUL='#005BAA', CELS='#00AEEF', VERDE='#2E7D32', ROJO='#C62828', NRNJ='#EF6C00';
```

Clases CSS estándar: `.kpi`, `.kpi.a` (alerta), `.val.r` (rojo), `.val.n` (naranja), `.rol-tag`, `.rol-si`, `.rol-no`, `.rol-par`, `.sb-wrap`, `.sb-bar`, `.escenario`, `.escenario.ret`, `.escenario.ven`, `.escenario.sal`

---

## Flujo de aprobación

1. Construir borrador en archivo `draft_[jugador]_comparables.html` separado
2. Mostrar al usuario — **no tocar el informe principal hasta recibir OK explícito**
3. Con OK: insertar contenido en `analisis_[jugador].html`, actualizar footer con nuevas fuentes, agregar script del chart `ch-roles`
