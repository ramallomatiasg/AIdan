# P40 — Tendencia semanal en cripto (time-series momentum): criterio declarado ANTES de medir (12-nov-2026)

**Hipótesis (Liu & Tsyvinski 2021; Moskowitz, Ooi & Pedersen 2012):** en cripto el retorno de las últimas semanas
anticipa el de la próxima (inversores que llegan tarde, flujos que siguen al precio). En FX el momentum semanal
(Fase 4 E4) murió por costo; en cripto el movimiento semanal es 10-20 veces el costo. Escalera A-B.
**Riesgo declarado:** que sea solo exposición a la suba de cripto ⇒ se compara contra "siempre largo" ajustado por
riesgo y contra un placebo con la misma exposición.

## Datos
- `.cache_p15/{SYM}.json` (Binance, ya bajado): precio de apertura del perpetuo cada 8 h y funding real cada 8 h.
  Principales: BTC, ETH, SOL, BNB, XRP, DOGE. **Reservados (nunca mirados para esto):** ADA, LINK, LTC, AVAX.
  Antes de declarar solo se miró el formato (no retornos).

## Regla (fija)
- Cada **lunes 00:00 UTC**: si el retorno del perpetuo de las 4 semanas previas (28 días) es > 0 ⇒ largo esa moneda
  la semana; si no ⇒ afuera. Cartera = promedio igual de las monedas con datos (las que están afuera aportan 0).
- **Costo:** 0,07% por lado (taker 0,05% + deslizamiento 0,02%) cada vez que una moneda entra o sale; el largo
  **paga** el funding real de la semana (cobra si es negativo).

## Muestras
- Descubrimiento: semanas de 2020 a 2022. Reserva: semanas desde el 2-ene-2023 hasta el último lunes con semana
  completa en el cache. Fuera de muestra adicional (solo si PASA): las 4 monedas reservadas, mismo período completo.

## Control
- **Siempre largo** las mismas monedas (paga funding, un solo costo de entrada).
- **Placebo:** 2000 carteras donde cada moneda está larga al azar con la MISMA fracción de semanas que la regla en esa
  muestra ⇒ percentil 95 del Sharpe.

## Criterios (PASA = los 5, sobre la reserva salvo que diga otra cosa)
1. n ≥ 150 semanas en la reserva.
2. Media semanal neta > 0 y extremo inferior del CI95 (bootstrap por bloques de 4 semanas) > 0.
3. Media semanal neta > 0 también en el descubrimiento.
4. Sharpe anualizado de la regla > Sharpe de siempre largo.
5. Sharpe de la regla > percentil 95 del placebo.

## Descriptivo (no decide)
Por moneda, por año, caída máxima, fracción de semanas invertido, costo y funding pagados.

## Si PASA
No se activa. Siguiente: monedas reservadas, luego papel en vivo; propuesta al user.
## Si NO PASA
Cerrar momentum de series de tiempo semanal en cripto. No probar otro plazo (2/8/12 semanas) ni otra cesta.
