# P11 — carry con filtro de tendencia (semanal) — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "probá lo restante"). **Tool:** `tools/backtest_p11_carry.py` (read-only,
sin MT5, no toca la DB). Lee `.cache_fase2/M5_500000` y la tabla de tasas `docs/p11_policy_rates.csv` (fuentes en
`docs/p11_policy_rates_fuentes.md`, armada el 23-oct con fuentes de los bancos centrales).

## Pregunta

Carry = quedarse del lado del par que COBRA intereses. Es la única familia de FX con premio documentado
(Lustig-Verdelhan, Menkhoff et al. 2012) que no depende de adivinar el precio de corto plazo, y sus pérdidas
vienen en caídas bruscas cuando hay pánico; el filtro de tendencia busca evitarlas. **¿Carry + tendencia tiene
neto positivo en 2020-2026, con el swap REAL que cobra esta cuenta?**

## Reglas (congeladas)

- **Universo:** los 20 pares de Fase 1; precios D1 re-muestreados desde M5 (como P2).
- **Rebalanceo semanal:** el primer día hábil de cada semana, en la primera vela M5 ≥ 01:00 server (fuera del
  rollover).
- **Carry del par** XXX/YYY = tasa(XXX) − tasa(YYY), con las tasas a fin del mes ANTERIOR (sin mirar el futuro).
- **Tendencia:** retorno de los últimos 60 días D1 hasta el cierre anterior al rebalanceo.
- **Posición:** largo si carry ≥ +0,5 pp **y** tendencia > 0; corto si carry ≤ −0,5 pp **y** tendencia < 0;
  si no, afuera. Se mantiene hasta el próximo rebalanceo.

## Costos y swap

- Al abrir o cerrar: media comisión Raw del spec + el spread de la vela (piso 0,1p). Si la posición sigue igual
  de una semana a la siguiente, no se cobra nada.
- **Swap histórico reconstruido:** swap teórico por noche = (tasa XXX − tasa YYY)/100/360 × precio, del lado
  correspondiente, menos el **recargo del broker** calibrado contra el swap REAL del spec (snapshot 18-ago-2026)
  frente a las tasas de 2026-08: `recargo = teórico(2026-08) − swap_spec`, por par y por lado, constante en el
  tiempo. Miércoles ×3, sábado/domingo 0.

## Métrica

Retorno neto por posición-semana, en % del precio. Para el CI se agrega por SEMANA (media de los pares activos
esa semana) y se bootstrapea sobre semanas: las posiciones de una misma semana están correlacionadas.

## Control

Mismas semanas y mismos pares activos con **dirección al azar** (swap y costos del lado que toque), 1.000
réplicas.

## Criterio de PASA (los 5)

1. n ≥ 300 posiciones-semana.
2. Media semanal neta > 0 con CI95 bootstrap (sobre semanas) cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control.
5. ≥ 12 de 20 pares con suma neta > 0 (entre los que tuvieron posición).

Descriptivos (no deciden): carry solo (sin tendencia), tendencia sola (sin carry), y cuánto del neto es swap vs
precio.

**Si pasa:** los 6 reservados, una vez. Y queda el choque con la cuenta: posiciones de semanas con stops anchos
⇒ con lote mínimo 0,01 hace falta ~$10k para arriesgar ~1% (decisión de capital, no de código).
**Si no pasa:** cerrado carry + tendencia en FX sobre esta data; no se barren umbral de carry, ventana ni
frecuencia.

## Límites

Tasas de política, no las tasas interbancarias que usa el broker. El recargo del broker puede haber cambiado en
el tiempo. 2020-2026 tuvo tasas ~0 en casi todos lados hasta 2022 ⇒ la mitad 1 tiene poco carry por construcción.
