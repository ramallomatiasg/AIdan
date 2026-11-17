# P45 — carry de funding de Hyperliquid (P21-A) en otras monedas, reglas congeladas — criterio declarado ANTES de medir

**Fecha:** 16-nov-2026 (investigación diaria, primera propuesta "en cola" de `docs/propuestas_registro.md`).
**Tool:** `tools/backtest_p45_hl_otras_monedas.py` (read-only, sin MT5, no toca la DB). Datos PÚBLICOS:
funding horario y velas de 8 h de Hyperliquid (`api.hyperliquid.xyz/info`) y spot de 8 h de Binance, a `.cache_p45/`.
Reusa el motor `simulate` de P15 y la configuración de P21-A (importados, no copiados).

## Pregunta

P21-A (spot en Binance + perpetuo vendido en Hyperliquid) pasó en 6 monedas y en 4 reservadas, pero son las 10
monedas más grandes. Si el premio es estructural (los apalancados de HL pagan por estar largos), tiene que aparecer
en monedas que nunca se usaron. Si no aparece, el pase era de las grandes.

## Universo (fijado por volumen ANTES de mirar el funding)

Foto del volumen de 24 h de Hyperliquid tomada hoy (`.cache_p45/hl_volume_snapshot.json`). Regla mecánica: en orden
de volumen, saltear las 10 de P21, exigir par spot `XXXUSDT` operando en Binance (`kPEPE` → `PEPE`) y primer funding
en HL ≤ 22-oct-2025 (al menos un año de historia). Se toman las primeras 15 (`.cache_p45/universe.json`):

HYPE, ZEC, NEAR, PUMP, kPEPE, ENA, UNI, XPL, ASTER, WLD, ZRO, AAVE, JUP, TRUMP, TAO.

(Salteadas por no tener spot en Binance: LIT, XMR, VVV, CASHCAT, SKR, FARTCOIN.) Solo se miró la fecha del primer
funding, no su valor.

## Reglas (las de P21-A, sin cambios)

Período 2023-05-12 → 2026-10-22. Decisión cada 8 h; señal = media de 7 días del funding horario de HL por 8 h;
entrar ≥ 0,005%, salir < 0; costo 0,37% de ida y vuelta; capital 2 × nocional; rebalanceo ±50%. Una moneda opera
desde que hay spot de Binance y perpetuo de HL en la misma vela y 7 días de funding.

**Único cambio declarado (no es de la regla, es de la cartera):** en P21 las 6 monedas existían desde el arranque;
acá muchas empiezan en 2024-25. Promediar con ceros antes de que exista la moneda diluiría el premio. Por eso la
cartera reparte el capital **entre las monedas disponibles en cada período** (las que ya cumplen la condición de
arriba). La versión con ceros (la de P21) se reporta como descriptivo.

## Criterio de PASA (los 5 de P21, adaptados a 15 monedas)

1. Rendimiento anualizado sobre el capital > tasa libre media del período (`docs/p11_policy_rates.csv`, USD).
2. CI95 por bootstrap en bloques de una semana: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima < 10%.
5. ≥ 10 de 15 monedas con neto > 0.

**Descriptivo (no decide):** cartera con ceros (P21), "siempre adentro", por año, por moneda, y el costo con
deslizamiento triple (0,05% por lado y pata ⇒ 0,49%), porque en monedas chicas on-chain 0,02% es optimista.

**Si pasa:** el premio de HL no depende de las 10 grandes ⇒ propuesta al user de sumar monedas al libro de papel de
P19 (sin activar nada). **Si no pasa:** el carry de HL queda limitado a las grandes; no se barren umbrales, ventana
ni lista de monedas.

## Límites

- La lista sale del volumen de HOY: las monedas que murieron en el camino no están (sesgo de supervivencia, a favor).
- Monedas nuevas pueden tener funding muy alto en el lanzamiento con riesgo de "squeeze" de la pata corta que el
  motor (velas de 8 h, sin liquidación) no ve; la caída máxima se mide con la marca de 8 h.
- Riesgo de exchange y de puente no modelados (igual que P21).
