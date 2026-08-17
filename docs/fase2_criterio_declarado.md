# Fase 2 — criterio DECLARADO ANTES de correr el backtest

**Fecha/hora de declaración: 17 Ago 2026, antes de ejecutar una sola línea del test.**
**Commiteado antes de la corrida. Si este archivo se modifica después de ver resultados,
el hallazgo no vale nada.**

---

## 1. Qué pregunta responde (y qué NO respondió la Fase 1)

La Fase 1 (commit `579cc22`) midió el detector `detect_structure_signals` sobre **velas D1**
en 21 pares y 7+ años, y no encontró edge: pooled −0,64 p/trade neto de comisión (PF 0,99),
−3,76 con swap (PF 0,93), sobre n=3.669.

De ahí el commit concluyó:

> *"el detector medido es el MISMO que alimenta structure, m15 y h1 en vivo […] El problema
> no son los filtros ni la gestión: es el generador de señal."*

**Esa conclusión es una EXTRAPOLACIÓN, no una medición.** El test corrió sobre D1; los tracks
vivos corren sobre M5/M15/H1. Nadie midió el detector, a través de instrumentos, en el
timeframe donde realmente opera.

**Fase 2 mide exactamente eso.**

### Debilidades reconocidas de la Fase 1, anotadas acá para no repetirlas

1. **8 de 21 NO es "menos que el azar".** Con p=0,5 se esperan 10,5 con desvío 2,29 ⇒ 8 está a
   1,1 desvíos. Es ruido. El titular del commit sobrevendió ese número. **En Fase 2 el conteo
   de pares positivos queda degradado a DESCRIPTIVO y no forma parte del criterio.**
2. **Los 21 pares no son 21 experimentos independientes.** Salen de 8 monedas; la dimensión
   independiente real es ~7. El pooled es la métrica válida, no el conteo.
3. **Las constantes del detector están en pips de EUR/USD M5** y se aplicaron sin escalar a
   pares que se mueven 10x más. Se reconoce como límite (ver §9), no se "arregla" acá porque
   escalar por ATR ya se probó en H4/D1 y **empeoró** (PF 1,40 → 1,02).

---

## 2. Universo — CONGELADO, no se re-elige

**Ver ENMIENDA 2: la descripción original de este apartado era factualmente incorrecta.**

Los **26 pares** que salen de unir las dos listas pre-declaradas y ya commiteadas:
los **20** de `docs/fase1_pares_declarados.md` (commit `5a7d57e`) más los **6**
out-of-sample de `docs/fase1b_prediccion_registrada.md` (commit `2269691`).
No se agrega ni se saca ninguno por performance.

**Los 20 de Fase 1** — majors (7): EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY ·
crosses (13): EURGBP, EURJPY, EURCHF, EURAUD, EURCAD, EURNZD, GBPJPY, GBPCHF, GBPAUD, AUDJPY,
AUDNZD, AUDCAD, CADJPY

**Los 6 de Fase 1b** (out-of-sample, con predicción registrada): CHFJPY, NZDJPY, GBPNZD,
NZDCHF, NZDCAD, GBPCAD

**Única razón admitida para excluir un par: falta de historia** (< 100.000 velas M15
disponibles). Si pasa, se reporta **cuál y por qué ANTES de mirar cualquier resultado**, en
este mismo archivo.

---

## 3. Test PRIMARIO — uno solo

| Dimensión | Valor declarado |
|---|---|
| Timeframe | **M15** |
| Velas por par | **500.000** (≈ 20,2 años, jun-2006 → ago-2026) |
| Variante | **`naive`** — constantes en pips SIN escalar |
| Params | **`live`** (los reales de `optimizer_params`, no los default) |
| Sesión | **`sweep`** — las 4 sesiones, criterio exigido en **CADA UNA** (ver ENMIENDA 1) |

**Por qué M15 y no M5:** al mismo costo de cómputo (500k velas/par), M15 da **20,2 años** y M5
da 6,7. M15 cubre 2008, 2015, 2020 y 2022 — cuatro regímenes de crisis distintos. Y
`m15_structure` es un track VIVO, no una analogía.

**Por qué `naive` y no `scaled`:** porque `naive` es literalmente lo que corre en producción.
La pregunta es "¿el sistema que tengo tiene edge?", no "¿podría tenerlo otro sistema?".

**Por qué `sweep`:** lección de v3.54.1. El paso 7 de `dynamic_conf` suma el `conf_adj` de
sesión, que corre contra `min_confidence=60` y por lo tanto **mueve la población entera** de
señales. Correr una sola sesión hace que el resultado dependa de la hora en que se ejecutó el
script.

> **Cláusula de cómputo, declarada ahora:** si la medición de tiempo (solo cronómetro, sin
> mirar ningún resultado) muestra que la corrida es inviable, **se reduce la cantidad de velas
> por par — nunca el sweep, nunca la lista de pares.** La reducción se escribe en este archivo
> ANTES de correr, con el número exacto.
>
> **Resultado de la medición (17 ago, antes de correr, solo cronómetro):** 193 velas/seg por
> core; 20 cores disponibles. M15/500k × 21 pares × 4 sesiones = 42 M llamadas ≈ **4,3 h con 14
> workers**. **Viable ⇒ NO se reduce la ventana. El criterio queda como está declarado.**

---

## ENMIENDA 1 — hecha ANTES de correr, sin ningún resultado a la vista

**Qué decía:** *"sesión sweep, criterio sobre el **pooled de las 4**"*.

**Por qué estaba mal:** las 4 sesiones **no son 4 muestras independientes**. Son 4 supuestos
alternativos sobre la misma realidad — el mismo trade aparecería hasta 4 veces. Poolearlas
infla el n de forma artificial y promedia mundos que no coexisten.

**Qué dice ahora:** el criterio de §6 se evalúa **en cada sesión por separado y debe cumplirse
en las CUATRO**. Es el mismo tratamiento que la v3.54.1 le dio al baseline del D1: *"si el
resultado aguanta las cuatro, el baseline es robusto a esta perilla; si solo vive en una, el
titular dependía de la hora del reloj"*.

**Por qué esta enmienda no es un ajuste conveniente:** el criterio nuevo es **más estricto**
que el que reemplaza (antes bastaba un agregado; ahora tienen que dar las cuatro). Una enmienda
que se hace más difícil de aprobar no puede estar motivada por querer aprobarla.

**Trazabilidad:** commiteada antes de ejecutar una sola línea del test, en un commit separado
del que creó este archivo. Sin resultados a la vista.

---

## ENMIENDA 2 — también ANTES de correr, sin resultados a la vista

### 2.a — El universo estaba mal descrito

**Qué decía §2:** *"los mismos 21 pares de `fase1_pares_declarados.md` (los 20 declarados +
EURUSD)"*. **Es falso: EURUSD ya está entre los 20.**

Lo que realmente pasó en Fase 1: de los 20 declarados corrieron **15** (el resto no pasó el
mínimo de velas D1), y Fase 1b agregó **6 out-of-sample** ⇒ 15 + 6 = los 21 del titular.

**Qué dice ahora:** el universo es la **unión de las dos listas pre-declaradas = 26 pares**.
Las dos fueron declaradas y commiteadas antes de ver ningún resultado, así que ninguna está
contaminada por performance. Es un **superconjunto** de los 21 de Fase 1, no un recorte.

### 2.b — El perfil de SL/TP/hold no estaba fijado, y decide el resultado

El criterio no decía con qué SL/TP/hold simular en M15. Hay dos opciones legítimas que
responden preguntas distintas, así que se declara cuál es cuál **ahora**:

| | Perfil | Responde |
|---|---|---|
| **PRIMARIO** | El **vivo de M15** (`technical_m15.py:M15_PROFILE`): **SL 15p, TP 60p, hold 3 velas** (= expiry 45 min) | *"¿el sistema que YO corro tiene edge?"* |
| **SECUNDARIO** | El del arnés de Fase 1: **`sl_atr_mult` 1,2 · `rr` 2,0 · hold 10 velas** | *"¿es comparable manzana-con-manzana contra Fase 1?"* |

**Primario = el vivo**, por coherencia con el principio ya declarado en §3 para elegir `naive`:
*"la pregunta es «¿el sistema que tengo tiene edge?», no «¿podría tenerlo otro sistema?»"*.

**Límite declarado ahora:** el `tp_cap = max(ATR,2)*2` de producción (`technical.py:1430`), que
en vivo recorta el TP nominal de 60p a ~18p, **NO se replica** en la simulación. El efecto neto
sobre el resultado es ambiguo (un TP más grande pega menos veces pero paga más), y por eso se
deja dicho en vez de estimado.

### Por qué estas dos correcciones tampoco son convenientes

2.a **agranda** el universo (26 en vez de 21) e incluye obligatoriamente los 6 pares
out-of-sample que en Fase 1 salieron casi todos negativos. 2.b elige como primario el perfil de
**hold más corto** (3 velas contra 10), que es el más hostil a que aparezca un edge. Ninguna de
las dos le hace el test más fácil al detector.

---

## ENMIENDA 3 — antes de correr: tope de muestra del bootstrap

**Motivo (medido en el smoke test de plomería, sin mirar P&L):** el detector dispara en el
**24,5% de las velas**. A 500.000 velas × 26 pares eso da **~3,2 millones de trades por
sesión**, no miles. Un bootstrap de 10.000 reps sobre 3,2 M serían 3,2 × 10¹⁰ sorteos por
sesión: inviable.

**Qué cambia:** si n > **250.000**, el CI se calcula sobre una submuestra aleatoria (semilla
fija) de 250.000 trades.

**Por qué no es conveniente:** menos datos ⇒ **CI más ancho** ⇒ la condición §6.2 (límite
inferior > 0) se vuelve **más difícil** de cumplir, nunca más fácil.

**Nota estadística para leer el resultado:** con n de este orden el error estándar de la media
es minúsculo (~0,01 pips). Eso significa que **§6.2 es casi automática si §6.1 se cumple**: a
esta escala "significativo" no cuesta nada. El poder discriminante real del criterio está en
**§6.3 (las dos mitades)** y sobre todo en **§6.4 (el control aleatorio)**. Un resultado que
pase 1 y 2 pero no 4 **no es un edge: es ruido con n grande.**

---

## 4. Métrica primaria

**Pooled avg pips/trade neto de comisión y de swap**, sobre todos los trades de los 21 pares.

- **Comisión:** por símbolo, estimada con `trade_tick_value / trade_tick_size` (IC Raw
  ~$3,50/lote/lado). Si MT5 no la da para un símbolo, se cae al 0,8p de EUR/USD **y se dice en
  el reporte**, no en silencio.
- **Swap:** por par Y por lado, leído de `symbol_info`, aplicado por noche efectivamente
  mantenida según la dirección real del trade.
- **CI 95%:** bootstrap por percentiles sobre los trades, **10.000 remuestreos**. No
  aproximación normal: la distribución de P&L es asimétrica.

---

## 5. Control aleatorio — REQUISITO, no adorno

Esto es lo que faltó en la Fase 1b, y el propio commit lo anotó como falla de diseño:

> *"un criterio de conteo de signos necesita siempre su comparación contra la constante,
> declarada junto con él. No la declaré."*

**Especificación del control (declarada ahora para que no sea ajustable después):**

- Misma **cantidad de entradas por símbolo** que produjo el detector.
- Momentos de entrada **sorteados uniformemente** del mismo universo de velas (mismo símbolo,
  mismo período).
- Dirección sorteada **respetando el ratio long/short que el detector produjo en ese símbolo**.
  Esto es deliberado: controla por la deriva direccional del par, de modo que lo que se mide es
  si el detector aporta **selección y timing**, no si el par subió.
- **Mismo SL/TP/hold**, calculados idénticamente desde el ATR de la vela de entrada sorteada.
- Mismos costos (comisión + swap) aplicados igual.
- **200 remuestreos** ⇒ distribución del pooled avg/trade bajo azar.

**El detector debe superar el percentil 95 de esa distribución.**

---

## 6. Criterio de éxito — las CUATRO condiciones, todas

Para poder decir **"pasa"**, en **CADA UNA de las 4 sesiones** (ENMIENDA 1):

1. Pooled avg/trade neto de costos **> 0**
2. **Límite inferior del CI 95% > 0** (bootstrap)
3. **Positivo en las DOS mitades** del período (walk-forward **temporal**: corte por fecha en
   el punto medio del período, no por posición en la lista de trades)
4. **Por encima del percentil 95** del control aleatorio

Si falla **cualquiera** de las cuatro condiciones, **en cualquiera de las 4 sesiones** → no pasa.

---

## 7. Secundarios y exploratorios — NO pueden dar veredicto solos

Se corren y se reportan **completos**, pero un resultado positivo en cualquiera de estos
**NO** habilita a decir "pasa". El veredicto declarado en ese caso es
*"no concluyente, necesita su propio test pre-registrado"*.

- M5 / 500.000 velas / `naive` (≈ 6,7 años)
- M15 / `scaled`
- M5 / `scaled`

Están degradados **a propósito**: probar 4 combinaciones y quedarse con la mejor es
exactamente cómo se fabrica un falso positivo.

---

## 8. Descriptivo — se reporta, NO es criterio

- Tabla de los 21 pares ordenada, **sin recortar los negativos**.
- Conteo de pares positivos (degradado por §1.1).
- Desglose por `setup_type`.
- Frecuencia de señales por par.

---

## 9. Decisión comprometida ANTES de ver los números

| Resultado | Acción comprometida |
|---|---|
| **PASA** (las 4 condiciones) | La refutación del D1 **no** se extrapola al vivo. El generador tiene edge en el TF donde opera ⇒ el problema vuelve a ser costo/gestión, que sí es reparable. Se trabaja ahí. |
| **FALLA** e indistinguible del control | El generador está muerto en el timeframe donde opera. Se apagan `structure`/`m15`/`h1` y se pasa a SMC. |
| **AMBIGUO** (punto > 0 pero CI cruza, o las mitades no coinciden, o no supera el control) | **NO CONCLUYENTE. No se toca nada, NO se re-corta la data buscando algo.** Se pasa a SMC igual. |

La tercera fila es la que más protege. Es la trampa exacta en la que cayó el modelo de
Efficiency Ratio de la Fase 1b: in-sample Spearman +0,529, out-of-sample +0,086 (p=0,872).

---

## 10. Límites declarados ANTES, no descubiertos después

- Un backtest típico **infla 20-30%** vs real con fricción.
- Sin spread variable, sin slippage, sin latencia.
- Sin los filtros del loop vivo (SIM A, counter-HTF, anti-spam, cooldown, warmup) ⇒ la
  frecuencia real sería MENOR.
- `htf_bias = None` (no derivado de SMC live).
- Solo trigger `structure` (sin news / smc / pre_planned).
- Constantes en pips calibradas para EUR/USD aplicadas a pares de escala distinta (§1.3).

**Consecuencia declarada ahora: un "PASA" es permiso para investigar más, NUNCA permiso para
operar.** Si el límite inferior del CI apenas roza el cero por arriba, en la práctica es un no.

---

## 11. Compromisos anti-p-hacking

1. No se re-corta la data buscando un subconjunto que funcione.
2. No se agregan filtros después de ver resultados.
3. No se cambia la ventana, ni la lista de pares, ni la variante, después de ver resultados.
4. Se reportan **los 21 pares**, incluidos los que salgan mal.
5. Si el resultado es feo, se dice que es feo.

---

## 12. Hipótesis

**H1:** el detector tiene edge en M15 a través de instrumentos ⇒ la extrapolación de la Fase 1
era incorrecta y el problema del vivo es de costo/gestión.

**H0 (lo que se asume si la evidencia no alcanza):** el detector no genera señal con
información en ningún timeframe medido ⇒ la Fase 1 generalizaba bien, y el camino no es
seguir filtrando sino cambiar de generador.
