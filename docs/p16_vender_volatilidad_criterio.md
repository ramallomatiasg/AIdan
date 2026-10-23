# P16 — vender volatilidad (SVXY) solo con la curva del VIX en contango — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "declará y probá P16"). **Tool:** `tools/backtest_p16_vol.py` (read-only,
sin MT5, no toca la DB). Baja datos diarios PÚBLICOS de Yahoo Finance (sin cuenta) a `.cache_p16/`.

## Pregunta

La volatilidad implícita (lo que se paga por protegerse) suele estar por encima de la que después ocurre: quien
vende ese "seguro" cobra un premio documentado (prima de riesgo de volatilidad). Se cobra cayendo poco a poco y se
pierde de golpe en los pánicos (feb-2018: un producto así perdió >90% en un día). El filtro clásico para esquivar
lo peor: **estar adentro solo cuando la curva del VIX está en contango** (VIX < VIX3M = el mercado espera más
calma que la actual), y salir cuando se invierte. **¿Esa regla deja más que P15 (~5%/año) con un riesgo
aceptable?**

## Instrumento y datos

- **SVXY** (ETF de volatilidad inversa, operable con comisión 0 en brokers como Alpaca), oct-2011 → 23-oct-2026.
  Ojo: fue −1x hasta el 27-feb-2018 y −0,5x desde entonces; se usa tal cual (es lo que se podía operar).
- **^VIX y ^VIX3M** (señal), **SPY** (referencia), **^IRX** (tasa libre de riesgo, descriptivo).
- Precios ajustados por splits (open ajustado con el mismo factor que el close).
- **SVIX** (−1x, desde 2022) solo descriptivo con la misma regla.

## Regla (congelada)

- Señal al cierre del día t: **adentro si VIX / VIX3M < 1**; si no, afuera (efectivo a 0%, conservador).
- **Ejecución a la apertura del día t+1** (no se opera con el cierre que generó la señal).
- Costo: 0,05% por lado en cada entrada o salida (spread; comisión 0).
- Sin apalancamiento, todo el capital en una sola posición.

## Criterio de PASA (los 5, sobre oct-2011 → oct-2026)

1. Crecimiento anual compuesto (CAGR) ≥ **10%** (que deje claramente más que P15).
2. CI95 del rendimiento medio anualizado por bootstrap en bloques de 21 días: límite inferior > 0.
3. CAGR > 0 en las dos mitades cronológicas.
4. Caída máxima ≤ la de comprar y mantener SPY en el mismo período **y** Sharpe > el de SPY.
5. Peor mes calendario > −30%.

Descriptivos (no deciden): SVXY siempre adentro, SPY, por año, la peor semana de feb-2018, mar-2020 y ago-2024,
SVIX con la misma regla, y el resultado si el efectivo cobrara la tasa libre.

**Sin reservados:** hay un solo instrumento con historia larga y la regla es la estándar de la literatura (no
sale de mirar esta data). **Si pasa:** shadow en papel con datos en vivo (o paper trading de Alpaca) antes de
plata. **Si no pasa:** cerrada la venta de volatilidad con este filtro; no se barren umbral del ratio, otros
ETFs ni horarios.

## Límites

Spread real en los días de pánico puede ser mucho mayor que 0,05%. El −0,5x post-2018 hace que la segunda mitad
rinda por construcción menos que la primera. Datos de Yahoo: sin verificación contra otra fuente.
