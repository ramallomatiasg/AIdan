# P15 — carry de funding en cripto (delta-neutral) — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "arrancá con P15"). **Tool:** `tools/backtest_p15_funding.py` (read-only,
sin MT5, no toca la DB). Baja datos PÚBLICOS de Binance (sin cuenta ni clave) a `.cache_p15/`: historial de funding
de los perpetuos USDT-M y velas de 8 h de spot y perpetuo.

## Pregunta

En los perpetuos, cuando el funding es positivo los largos le PAGAN a los cortos cada 8 h. Con spot comprado y
perpetuo vendido por el mismo monto, el precio se cancela y queda el funding. **¿Ese cobro, neto de comisiones,
del costo de rebalancear y de lo que se mueve la base (spot vs perpetuo), le gana a dejar la plata en la tasa
libre de riesgo?** No es adivinar el precio: es cobrar un premio que pagan los apalancados.

## Universo (data verificada el 23-oct)

- **Principal:** BTC, ETH, SOL, BNB, XRP, DOGE (pares USDT de Binance; funding desde 2019-09 a 2020-09 según la
  moneda) hasta el 22-oct-2026.
- **Reservados (fuera de muestra, solo si pasa):** ADA, LINK, LTC, AVAX. No se bajan ni se miran antes.

## Reglas (congeladas)

- **Decisión cada 8 h** (00/08/16 UTC), con el funding conocido hasta ese momento (sin mirar el futuro).
- **Señal:** media del funding de los últimos 7 días, expresada por cada 8 h.
  **Entrar** si ≥ 0,005% (≈5,5% anual). **Salir** si < 0.
- **Posición:** compra spot y venta del perpetuo por el mismo nocional, al open de la vela de 8 h de cada uno.
- **Mientras está adentro:** cobra (o paga) cada funding del perpetuo, proporcional al precio del perpetuo en ese
  momento / el de entrada. El resultado de precio es spot_salida/spot_entrada − perp_salida/perp_entrada (lo que
  se mueve la base).
- **Capital:** 2 × nocional (spot pagado entero + margen del 100% en el perpetuo, sin apalancar). **Rebalanceo**
  forzado cada vez que el precio se mueve ±50% desde el último: se cobra un costo de ida y vuelta.
- **Costos:** comisión taker (spot 0,10% y perpetuo 0,05% por lado) + 0,02% de deslizamiento por lado y pata ⇒
  0,38% del nocional por ida y vuelta.
- **Cartera:** una ranura de capital igual por moneda; la ranura sin posición rinde 0 (conservador).

## Criterio de PASA (los 5, cartera de las 6 principales)

1. Rendimiento neto anualizado sobre el capital > **la tasa libre de riesgo media del período** (fed funds,
   `docs/p11_policy_rates.csv`).
2. CI95 por bootstrap en bloques de una semana del rendimiento medio: límite inferior > 0.
3. Rendimiento anualizado > 0 en las dos mitades cronológicas.
4. Caída máxima de la cartera < 10%.
5. ≥ 4 de 6 monedas con resultado neto > 0.

Descriptivos (no deciden): "siempre adentro", resultado por año, cuánto es funding vs base vs costos.

**Si pasa:** los 4 reservados una vez (pasa fuera de muestra si su rendimiento > 0 y > la tasa libre de riesgo);
con eso, **shadow en testnet** (Binance/Hyperliquid) antes de pensar en plata.
**Si no pasa:** cerrado el carry de funding sobre esta data; no se barren umbrales ni ventana.

## Límites

- **Riesgo de exchange no modelado** (una quiebra tipo FTX se lleva las dos patas).
- Las velas de 8 h no ven el deslizamiento real dentro de la vela; los precios de funding se aproximan con el
  precio del perpetuo de la vela.
- El funding de 2020-2021 fue excepcionalmente alto (mercado alcista con mucho apalancamiento); por eso se exige
  que pase en las dos mitades.
