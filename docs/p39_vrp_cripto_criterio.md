# P39 — Prima de volatilidad en BTC (DVOL de Deribit): criterio declarado ANTES de medir (12-nov-2026)

**Hipótesis:** en cripto la volatilidad implícita (lo que se paga por las opciones) suele estar por encima de la que
después se realiza, porque los apalancados compran protección y calls. Vender esa volatilidad cobra un premio por
riesgo (escalera **A**) que no depende de adivinar la dirección. En P16 (acciones, vía SVXY) el premio existía pero
el riesgo de cola lo volvió peor que comprar el índice.

## Datos
- **DVOL de BTC** (índice de volatilidad implícita a 30 días de Deribit, metodología tipo VIX), diario, API pública
  `get_volatility_index_data` (sin clave), desde que existe (~mar/abr-2021) hasta el 31-oct-2026. Antes de declarar
  solo se verificó que la API responde (no se miraron niveles).
- **Volatilidad realizada:** retornos logarítmicos de 8 h del spot de Binance (`.cache_p15/BTC.json`, ya bajado),
  anualizada: RV² = Σ r² × (365 / 30) sobre 30 días.

## Regla (fija)
- Cada 30 días desde el primer día con DVOL (ancla fija: el primer dato), a las 00:00 UTC.
- **Señal:** DVOL_t > RV de los 30 días previos ⇒ se vende volatilidad 30 días. Si no, afuera.
- **Resultado (proxy de un swap de varianza vendido, en puntos de volatilidad con nocional vega):**
  `pnl = (IV² − RV_sig²) / (2·IV)` × 100, con IV = DVOL_t/100 y RV_sig la realizada de los 30 días SIGUIENTES.
  Incluye la convexidad (cuando la realizada se dispara la pérdida crece más que lineal).
- **Costo:** 2 puntos de volatilidad por operación (ida y vuelta de un straddle ATM en Deribit, conservador);
  pesimista 4 puntos.
- Limitación declarada: es un proxy, no un backtest de opciones reales (sin cobertura delta discreta ni bid/ask
  histórico). Si pasa, el paso siguiente tiene que usar precios de opciones reales.

## Muestras
- Descubrimiento: entradas de 2021 a 2023. Reserva: entradas desde el 1-ene-2024.
- Fuera de muestra adicional (solo si PASA): DVOL de **ETH** con la misma regla, nunca mirado.

## Criterios (PASA = los 5)
1. n ≥ 15 operaciones con señal en la reserva.
2. Media neta > 0 en toda la muestra y extremo inferior del CI95 bootstrap > 0.
3. Media neta > 0 en descubrimiento y en reserva por separado.
4. Robustez del ancla: repitiendo la regla con las 30 anclas posibles (día 0..29), media neta > 0 en ≥ 25 de 30.
5. Media neta > 0 con el costo pesimista (4 puntos).

## Descriptivo (no decide)
Vender siempre (sin señal), % ganadas, peor operación, caída máxima acumulada en puntos, por año.

## Si PASA
No se activa. Siguiente: ETH fuera de muestra y precios reales de opciones de Deribit; propuesta al user.
## Si NO PASA
Cerrar la prima de volatilidad de cripto vía DVOL. No probar otro umbral, otro plazo ni filtros de tendencia.
