# Fase 3 — generadores candidatos DECLARADOS ANTES de medir ninguno

**Fecha: 18 Ago 2026.** Commiteado antes de escribir una línea de los generadores y antes de
correr el screen. Si esta lista o los parámetros se modifican después de ver resultados, el
hallazgo no vale nada.

---

## 1. Por qué existe esta fase

Fase 2 cerró todas las reparaciones derivadas de `detect_structure_signals`:

| Vía | Estado |
|---|---|
| Tiene edge y el costo se lo come | ❌ Es **peor que el azar** (26 M ops, M5 y M15) |
| Es cuestión de timeframe | ❌ Igual en los dos |
| Entrar en el pullback | ❌ Sin cruce en ningún horizonte (4,7 M señales) |
| Invertirlo | ❌ Pico +0,25 p contra 0,90 de costo |
| Escalar constantes por ATR | ❌ Refutado en H4/D1 (PF 1,40 → 1,02) |
| Horizonte más largo | ❌ Refutado en Fase 1 (D1) |

Y dejó dos hechos que orientan la búsqueda:

1. **La excursión del detector es simétrica** (`fav/adv` ≈ 0,98 en todos los horizontes) ⇒
   ninguna combinación de SL/TP sobre esas entradas da el 2,5:1 que se necesita.
2. **El detector dispara en volatilidad por debajo del promedio** (`fav` y `adv` menores que el
   azar en todos los horizontes) ⇒ elige el régimen donde la propia data ya midió que pierde.

**Fase 3 no repara nada: busca un generador distinto.**

---

## 2. El riesgo de "probemos todo", y cómo se controla

Probar N ideas y quedarse con la mejor **encuentra un ganador aunque no haya ninguno**. Con
umbral al percentil 95 y 20 pruebas, 1 pasa por azar puro. Así nacieron el ML, los gates y el
modelo ER de Fase 1b — los tres murieron después.

Tres controles, declarados ahora:

1. **Umbral al percentil 99** del control aleatorio, no 95. Con 9 candidatos, la expectativa de
   falsos positivos baja de ~0,45 a ~0,09.
2. **Reserva out-of-sample**: el screen corre SOLO sobre los **20 pares de Fase 1**. Los **6 de
   Fase 1b** (CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD) **no se miran** hasta que un
   candidato sobreviva. Es la misma partición que ya estaba declarada en `5a7d57e` / `2269691`,
   así que no la elijo yo hoy.
3. **Parámetros fijados a valores de manual, NO optimizados.** Cada generador tiene UN solo
   juego de parámetros, escrito abajo. No se barren rangos: barrer rangos es la otra forma de
   fabricar un falso positivo.

---

## 3. Qué mide el screen

Para cada generador, sobre cada señal, a horizontes de **3, 6, 12, 24, 48, 96 velas**:

- `close` = movimiento neto en pips a favor de la dirección de la señal
- `fav` / `adv` = máxima excursión favorable / adversa (diagnóstico)

**No se simula SL/TP a propósito.** Elegir SL y TP introduce parámetros que se pueden tunear;
el movimiento neto crudo es una medida sin supuestos. Un generador con edge real mueve el precio
a su favor **antes** de que se le elija la gestión.

### Criterio para pasar el screen — las tres, en el mismo horizonte

1. `close` medio **> 0,90 pips** (el costo de round turn)
2. `close` medio **por encima del percentil 99** del control de entradas aleatorias
3. **n ≥ 1.000** señales en los 20 pares

**El umbral 1 es alto a propósito y la mayoría va a fallar.** Es el número que hace falta para
que la cuenta no dé negativo: hoy el detector da −0,05 a −0,25 y el azar da ~0,00. Pedir 0,90 es
pedir un edge de verdad, no un empate.

**Un candidato que pasa el screen NO habilita a operar.** Habilita a pasar al arnés completo de
Fase 2 (costos reales, swap, 4 sesiones, dos mitades, control p95) y después a los 6 pares
reservados.

---

## 4. Los 9 candidatos — CONGELADOS

Todos operan solo sobre precio (open/high/low/close). Ninguno usa LLM, ni la DB, ni indicadores
que no se puedan calcular de las velas. Timeframe del screen: **M5**, 500.000 velas por par.

### Familia A — reversión (el opuesto conceptual del actual)

**A1. Z-score contra la media.** MA de 20 velas, desvío estándar de 20. Si
`(close − MA) / sd > +2` ⇒ **PUT**. Si `< −2` ⇒ **CALL**. (Entra CONTRA el desvío.)

**A2. Extremo de rango.** Si el `close` es el mínimo de las últimas 20 velas ⇒ **CALL**.
Si es el máximo ⇒ **PUT**.

**A3. Vela de agotamiento.** Pin bar: mecha ≥ 66% del rango de la vela y cuerpo ≤ 25%. Mecha
inferior larga ⇒ **CALL**; mecha superior larga ⇒ **PUT**.

### Familia B — expansión de volatilidad (lo único que la data propia dijo que discrimina)

**B1. Compresión → quiebre.** Si el rango de las últimas 10 velas es el más chico de las
últimas 100, entrar en la dirección de la primera vela que cierre fuera de ese rango.

**B2. ATR expandiendo.** Si `ATR(5) > 1,5 × ATR(20)`, entrar en la dirección del cuerpo de la
última vela.

### Familia C — tendencia real (no ruptura de nivel fractal)

**C1. Cruce de medias con pendiente.** MA(20) cruza sobre MA(50) **y** la pendiente de MA(50)
en 10 velas es positiva ⇒ **CALL**; simétrico ⇒ **PUT**.

**C2. Pullback a la media en tendencia.** MA(20) > MA(50) (tendencia arriba) **y** el precio
retrocede a tocar la MA(20) desde arriba ⇒ **CALL**; simétrico ⇒ **PUT**. *(Este es el
"pullback" bien hecho: contra una media, no contra niveles de un fractal de 2 vecinos.)*

### Familia D — estructura temporal

**D1. Rango de sesión asiática.** Rango entre 00:00 y 06:00 UTC; entrar en la dirección del
primer cierre fuera de ese rango, solo entre 06:00 y 12:00 UTC.

**D2. Rango del día previo.** Entrar en la dirección del primer cierre fuera del rango
`[low, high]` del día calendario anterior.

### Referencias en la misma tabla (no son candidatos)

- **REF-actual**: `detect_structure_signals`, para tener la referencia medida al lado.
- **REF-azar**: entradas aleatorias, mismo n y mismo ratio long/short por par.

---

## 5. Hipótesis y compromiso

**H1:** al menos uno de los 9 mueve el precio a su favor > 0,90 pips en algún horizonte, por
encima del p99 del azar.

**H0 (lo que se asume si la evidencia no alcanza):** ninguna de estas 9 familias tiene edge
extraíble en M5 sobre los 20 pares ⇒ el problema no es *cuál* de estos generadores se usa, y la
búsqueda de edge en precio a horizonte intradiario queda sin candidatos vivos. Eso **no** prueba
que no exista edge en ningún lugar; sí cierra esta familia de búsqueda.

**Compromiso:** se reportan **los 9**, con su número, incluidos los que salgan mal. Si ninguno
pasa, se dice que ninguno pasó, y no se re-cortan los datos buscando un subconjunto que
funcione.
