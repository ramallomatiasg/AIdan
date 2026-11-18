# P52 — carry de funding de P15 en ETH con la pata larga en WBETH de Binance — criterio declarado ANTES de medir

**Fecha:** 17-nov-2026 (investigación diaria). **Tool:** `tools/backtest_p52_wbeth_carry.py` (read-only, sin MT5,
no toca la DB). Motor `simulate` de P15 importado, sin cambios. Reemplaza a P48 (invalidada por el ruido del cociente
stETH/ETH de DefiLlama).

## Pregunta

P15 en ETH cayó casi a cero en 2025-26 porque bajó el funding. WBETH es ETH en staking de Binance: su precio en ETH
sube solo (~3%/año) con las recompensas. Si la pata larga es WBETH, se cobra funding + staking. ¿Eso le gana a la
tasa libre, sin que el descuento de WBETH contra ETH se coma el premio?

## Datos (verificados el 17-nov, antes de medir: solo existencia y primeras velas)

- ETH spot y perpetuo de 8 h + funding de Binance: `.cache_p15/ETH.json` (el de P15).
- Velas de 8 h de `WBETHETH` de Binance (API pública `data-api.binance.vision`), listado el 12-may-2023. La vela de
  listado tiene un máximo de 2,22 (relleno, la lección de P45) ⇒ **se descartan los primeros 7 días del par**.
- Cache en `.cache_p52/`.

## Regla (la de P15, congelada)

Señal y umbrales de P15 (media de funding de 7 días ≥ 0,005% por 8 h para entrar, < 0 para salir), decisión cada
8 h, capital 2 × nocional, rebalanceo ±50%. Única diferencia: la pata larga vale `ETH_spot(t) × WBETHETH_open(t)`
(open de la vela de 8 h del mismo instante). Costo: el de P15 (0,38%) + 0,05% por lado por el libro más fino de
WBETH ⇒ **0,48%** de ida y vuelta.

**Control de datos (aborta, no decide):** si entre dos velas de 8 h consecutivas el cociente se mueve más de 2%, el
tool aborta y la medición queda inválida (el error de P48 no se repite en silencio).

## Muestra

- **Descubrimiento:** 26-may-2023 (listado + 7 días de descarte + 7 días de ventana) → 31-dic-2024.
- **Reserva:** 1-ene-2025 → 22-oct-2026. Se mira solo si pasa el descubrimiento.

## Criterio de PASA (descubrimiento, todos)

1. Rendimiento anualizado sobre el capital > tasa libre media del período (`docs/p11_policy_rates.csv`, USD).
2. CI95 por bootstrap en bloques de una semana: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima < 10%.

**Reserva:** anualizado > tasa libre media de 2025-26. **Descriptivo (no decide):** P15 en ETH sin staking en los
mismos tramos, cuánto aporta el staking (crecimiento del cociente), mínimo del cociente, "siempre adentro".

**Si no pasa:** cerrado el carry de funding con ETH en staking; no se barren umbrales ni se cambia de token.

## Límites

- Una sola moneda ⇒ sin criterio de "monedas > 0". No incluye un evento de estrés tipo jun-2022 (el par no existía).
- Riesgo de exchange y de custodia del staking de Binance no modelados.

**Enmienda 1 (17-nov, antes de medir el descubrimiento):** la 1ra corrida abortó por el control de datos en la
**reserva** (salto de 3,1% del cociente el 11-oct-2025 00:00 UTC). Es el desacople real de WBETH en el desplome del
10-oct-2025 (Binance compensó a los usuarios), no ruido. El control se aplica ahora **al tramo que se mide**: el
descubrimiento se mide solo si su tramo no tiene saltos > 2%. Si el descubrimiento pasa, en la reserva ese evento se
incluye tal cual (es exactamente el riesgo de cola que hay que medir) y el control solo aborta por saltos que no
vuelven dentro de las 3 velas siguientes. No se miró ningún resultado; reglas, umbrales y criterios no cambian.
