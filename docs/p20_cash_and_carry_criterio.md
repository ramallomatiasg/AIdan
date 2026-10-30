# P20 — cash-and-carry con futuros TRIMESTRALES de cripto — criterio declarado ANTES de medir

**Fecha:** 30-oct-2026 (rutina semanal, Parte 3: primera propuesta ejecutable de la cola; P7 espera a Leo y
P8 está bloqueada por muestra). **Tool:** `tools/backtest_p20_cash_carry.py` (read-only, sin MT5, no toca la
DB). Baja datos PÚBLICOS de Binance (sin cuenta ni clave) a `.cache_p20/`: velas diarias de spot y de los
futuros trimestrales USDT-M (`fapi/v1/continuousKlines`, `CURRENT_QUARTER` y `NEXT_QUARTER`).

## Pregunta

P15 (carry de funding con el perpetuo) pasó, pero en 2025-26 quedó por debajo de la tasa libre porque el
funding cambia todos los días. Con un futuro con vencimiento la base se FIJA al entrar: comprar spot y vender
el futuro, mantener hasta el vencimiento, y al vencer el futuro converge al spot. **¿Esa base pactada, neta de
costos, le gana a la tasa libre de riesgo, también en los últimos años?**

## Universo (data verificada el 30-oct)

- **Principal:** BTCUSDT y ETHUSDT trimestrales USDT-M (data desde feb/mar-2021) hasta el 29-oct-2026.
- **Sin reservados honestos:** USDT-M solo lista trimestrales de BTC y ETH. Los COIN-M (BTCUSD/ETHUSD, desde
  jun-2020) son el mismo premio en el mismo período ⇒ solo **descriptivo**, no cuentan como fuera de muestra.

## Reglas (congeladas)

- **Decisión diaria** al open de la vela de 00:00 UTC, con precios de ese open (sin mirar el futuro).
- **Contrato:** el `CURRENT_QUARTER` si faltan ≥ 14 días a su vencimiento; si faltan menos, el `NEXT_QUARTER`.
  Vencimiento = último viernes de mar/jun/sep/dic, 08:00 UTC. Nunca se entra el día del vencimiento.
- **Señal:** retorno pactado neto = F/S − 1 − costo de ida y vuelta. **Entrar** si ese retorno anualizado
  (× 365 / días al vencimiento) > tasa libre de ese mes (fed funds, `docs/p11_policy_rates.csv`).
- **Mantener hasta el vencimiento.** Al vencer se cobra F_entrada/S_entrada − 1 (el futuro liquida al índice ≈
  spot). Se puede volver a entrar ese mismo día con el contrato siguiente.
- **Salida forzada (riesgo de liquidación):** el futuro corto tiene margen del 100% del nocional; si el futuro
  sube ≥ 80% desde la entrada, se cierran las dos patas al open de ese día (se realiza la base del momento) y se
  paga otra ida y vuelta.
- **Costos:** igual que P15: comisión taker spot 0,10% y futuro 0,05% por lado + 0,02% de deslizamiento por lado
  y pata ⇒ **0,38% del nocional por ida y vuelta** (la liquidación al vencer se cobra como un lado más).
- **Capital:** 2 × nocional (spot pagado entero + margen del 100%). Una ranura igual por moneda; la ranura sin
  posición rinde 0 (conservador). Valor marcado a mercado diario = spot − futuro relativo a la entrada.

## Criterio de PASA (los 5, cartera BTC+ETH)

1. Rendimiento neto anualizado sobre el capital > **tasa libre media del período**.
2. CI95 por bootstrap en bloques de una semana del rendimiento diario medio: límite inferior > 0.
3. Rendimiento anualizado > 0 en las dos mitades cronológicas.
4. Caída máxima de la cartera < 10%.
5. Las 2 monedas con resultado neto > 0.

**Descriptivos (no deciden):** por año (sobre todo 2025-26, que es la razón de P20), base anualizada media
disponible, % del tiempo adentro, comparación con P15 en el mismo período, COIN-M.

**Si pasa:** shadow en papel como P19 (foto diaria de la base en vivo) antes de cualquier plata.
**Si no pasa:** cerrado el cash-and-carry trimestral sobre esta data; no se barren umbral, días mínimos ni
contrato.

## Límites

- Velas diarias: el precio de entrada es el open, sin deslizamiento real dentro de la vela.
- El futuro liquida al índice (promedio de varios exchanges), no al spot de Binance: diferencia ignorada.
- **Riesgo de exchange no modelado** (las dos patas en el mismo lado).
- La serie continua puede tener saltos en el cambio de contrato; el tool verifica que el `CURRENT_QUARTER` de
  la fecha corresponda al vencimiento calculado (si la base salta >5% de un día a otro, se marca y se reporta).

**Enmienda 1 (30-oct, DESPUÉS de una primera corrida, por un bug de datos — declarado):** la serie continua
`NEXT_QUARTER` de Binance repite el último precio los días en que el contrato siguiente todavía no cotiza (~505
días por moneda). El tool descarta un open idéntico al del día anterior (= sin dato). Reglas, umbrales y criterio
sin cambio; el resultado fue el mismo antes y después (+2,81%/año, NO PASA).
