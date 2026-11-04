# ¿Qué dato tiene información? — análisis y plan (4-nov-2026)

**Pedido del user (4-nov):** *"estamos atacando el problema que no es"*. Después de P27 (juez LLM con contexto
completo: no separa, el placebo separa igual), la pregunta deja de ser *cómo decidir mejor* y pasa a ser *qué dato
contiene información sobre el resultado*. Este documento ordena lo que ya se midió, explica por qué falló, lista las
fuentes que quedan y define la herramienta que lo responde (`tools/info_screen.py`, P29).

## 1. El diagnóstico en una línea

**Todo lo que se construyó desde abril optimiza la decisión sobre un insumo que no trae información del resultado.**
AIdan dispara rupturas en M5/M15 (cuando el movimiento ya ocurrió); filtros, confianza, calibración, ML y un juez LLM
intentaron separar las buenas de las malas mirando el mismo gráfico. Ninguno pudo, porque en esos 300 trades las
ganadoras (+$302) y las perdedoras (−$450) **no se distinguen en los datos que se miran** (P27: aprobadas −$0,58 vs
vetadas −$0,42; placebo igual).

## 2. Por qué el gráfico intradía se comporta como azar

- **Es información pública y la procesan miles de participantes más rápidos.** Un patrón de velas que anticipe 15 min
  a 3 h se arbitra hasta desaparecer; lo que queda es menor que el costo (estudio de falsificación del research §1:
  14 familias, ninguna pasa; Fase 2-6 acá: idem).
- **Lo que mueve el precio en ese plazo no está en las velas:** flujo de órdenes, posicionamiento, noticias.
- **El arnés no es el problema:** P0 inyectó un edge sintético y lo detectó (q≥0,60 pasa). Con señales reales no hay nada.
- **AIdan además entra tarde:** compra la ruptura ya hecha (agotamiento, 19-jun) y paga ~1,3 pips de costo sobre un
  movimiento medio de 2-3 pips.

## 3. De dónde sale una ventaja que sobrevive (taxonomía)

| Tipo | Por qué existe | Lo probado acá | Resultado | Lo que queda |
|---|---|---|---|---|
| **A. Premio por riesgo** (cobrar por asumir un riesgo que otro paga por sacarse) | Estructural: alguien paga el seguro | Carry FX (P11, P14), vender vol (P16), funding cripto (P15, P21), cash-and-carry (P20) | **Funding PASA** (también OOS); carry FX y vol no | Funding en vivo (P19, en papel); prima nocturna índices (P24) |
| **B. Proveer liquidez / flujos forzados** (cobrar por inmediatez a quien tiene que operar sí o sí) | Rebalanceos, fixings, vencimientos | Fin de mes FX (Fase 5), fixing (Fase 4 E3), pre-FOMC (P12) | Le ganan al azar pero no al costo, o ya arbitrados | Cambio de mes en índices (P25); estacionalidad horaria por instrumento (P29) |
| **C. Información que el precio todavía no tiene** | Llegar primero o mirar algo que otros no miran | News (track `news`), feed rápido (v3.61), calendar play (shadow), loop P22 (COT, tasas, VIX) | News pierde; P22 sin hallazgos que pasen reserva; calendar play sin muestra | Sorpresa de datos (calendar play), lead-lag entre activos (P29) |
| **D. Sesgos de comportamiento** (otros operan mal de forma repetible) | Sobre-reacción, momentum lento | Momentum semanal (Fase 4 E4), PEAD (P17), favorito-longshot (P18) | No pasan | — |
| **E. Patrones de precio intradía** | (si existieran, se arbitrarían) | structure, SMC, Leo, A1, rupturas, NR7, Donchian | **Nada pasa** | Cerrado |

**Lectura:** lo único que pasó es del tipo **A** (premio estructural). La categoría **E**, que es todo AIdan, está
cerrada con evidencia. Lo que vale la pena buscar está en **A, B y C**.

## 4. Un dato que sí es predecible y AIdan no usa: la volatilidad

La dirección intradía es ~azar, pero **el tamaño del movimiento no**: la volatilidad se agrupa (si la última hora se
movió mucho, la próxima también). Eso no da dirección, pero sirve para **no operar cuando el movimiento esperado no
cubre el costo** y para poner stops/objetivos del tamaño real. AIdan hoy usa pisos fijos en pips (m15: ATR ≥ 8p). El
screen lo mide explícitamente (bloque "riesgo") porque es la información más confiable que hay en el gráfico.

## 5. Opciones de prueba (ordenadas)

1. **P29 — screen de información (implementado hoy, `tools/info_screen.py`).** Antes de armar ninguna estrategia,
   mide si un dato anticipa el retorno siguiente, con descubrimiento → reserva, placebo y costo real por instrumento.
   Catálogo cerrado: estacionalidad por hora y día (B), lead-lag entre activos (C), volatilidad → tamaño del
   movimiento (riesgo), funding y base cripto (A), y dos controles de precio (momentum y reversión 2σ) para calibrar
   contra lo ya medido. **Solo lo que pase el screen pasa a backtest de estrategia.**
2. **P24 / P25 — prima nocturna y cambio de mes en índices** (B). Ya en la cola; el screen da una primera lectura.
3. **Funding en vivo (P19 + Hyperliquid).** Lo único que pasó. Lectura ene/feb-2027.
4. **Calendar play** (C). Necesita AIdan prendido antes de los datos (primer test real: NFP 6-nov).
5. **Juez de cierres** (la única vez que un LLM sumó: +58,8p en 29 CLOSE). No crea ventaja de entrada, puede recortar
   pérdidas. Re-prender en papel solo-manage (env, sin rebuild) si el user lo pide.

## 6. Lo que NO hacer

- Seguir poniendo filtros, confianza o IA arriba de las señales actuales de AIdan (categoría E).
- Buscar el mejor parámetro de algo que no pasó el screen.
- Mirar los reservados (6 pares de Fase 2, monedas reservadas de P15) antes de que algo pase en descubrimiento.
