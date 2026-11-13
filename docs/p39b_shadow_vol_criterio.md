# P39b — Shadow en papel de la prima de volatilidad (P39) con precios REALES de Deribit: criterio declarado ANTES de juntar (13-nov-2026)

**Por qué (OK del user, 13-nov):** P39 pasó con un proxy (DVOL contra realizada) que tiene tres reparos: el premio se
achicó (2025-26 negativo), el DVOL sobrestima lo que cobra un straddle real, y no hay historia gratis de precios de
opciones. La única forma de medir el costo real sin pagar es juntarlo hacia adelante. Mismo esquema que P19.

**NO OPERA.** Solo GET a endpoints públicos de Deribit y Binance, sin cuenta ni claves (test sobre el fuente). No toca
MT5 ni la DB de AIdan: escribe en `%APPDATA%/AIdan/state/vol_shadow.db`.

## Regla (congelada, la de P39)
- BTC y ETH, por separado. Ancla: 13-nov-2026. Ciclos de 30 días.
- **Entrada:** en la primera corrida desde la fecha del ciclo (y sin posición abierta en esa moneda): si el DVOL de
  las 00:00 UTC del día supera la volatilidad realizada de los 30 días previos (retornos de 8 h del spot de Binance,
  igual que P39) ⇒ se vende 1 straddle ATM. Si no ⇒ ese ciclo queda afuera (se registra).
- **Qué straddle:** el vencimiento con días hasta vencer más cercano a 30 dentro de [20, 45] (empate ⇒ el más largo);
  strike = el más cercano al precio subyacente (forward) de ese vencimiento con call y put listados.
- **Precio:** se vende al **bid** real de la call y de la put (no al mark). Prima a USD con el índice del momento
  (contabilidad en USD, como una cuenta en USD).
- **Cobertura delta diaria** con el perpetuo USDT de Binance: delta Black-76 calculado con la IV mark, el forward y
  el tiempo restante; en cada corrida se rebalancea al delta nuevo pagando 0,07% del nocional operado (taker 0,05% +
  deslizamiento 0,02%) y el funding real de Binance sobre la posición.
- **Comisiones de Deribit:** al entrar, por pata, mín(0,03% del subyacente, 12,5% del precio de la opción); al
  vencer, por la pata que termine adentro, mín(0,015% del subyacente, 12,5% de su valor).
- **Salida:** se mantiene hasta el vencimiento; liquida contra el `delivery_price` oficial de Deribit
  (pago del straddle vendido = |S − K|). Si una corrida no ocurre (PC apagada), ese día no se rebalancea (se registra
  el hueco; es parte del costo real de automatizar).
- **Resultado** por operación en USD por 1 BTC/ETH de nocional, en % del índice y en **puntos de volatilidad**
  (USD / vega de entrada), para compararlo con P39.

## Diagnóstico diario (no opera, junta muestra rápido)
Cada corrida, por moneda: straddle ATM a ~30 días ⇒ IV bid, ask y mark de la call y la put, DVOL del momento y
**brecha = DVOL − IV bid promedio del straddle**. Responde el reparo 2 en semanas, no en meses.

## Lecturas y decisión
- **~13-dic-2026 (30 días de diagnóstico):** si la mediana de la brecha es > 1,5 puntos en BTC **y** en ETH, la
  reserva de P39 (+1,5 netos) queda en cero o negativa con precios reales ⇒ llevar al user la propuesta de cerrar.
- **~13-may-2027 (6 meses):** lectura descriptiva (n ≈ 10-12 operaciones), sin veredicto.
- **~13-nov-2027 (12 meses), PASA = las 3:**
  1. n ≥ 18 operaciones cerradas (BTC + ETH).
  2. Media neta real > 0 en puntos de volatilidad **y** en USD.
  3. Real − proxy de P39 para las mismas operaciones, en promedio, ≥ −2 puntos (el proxy no exagera más que su costo).
  Si no pasa ⇒ borrar la tarea y cerrar P39. Si pasa ⇒ propuesta al user (abrir cuenta en Deribit es decisión suya).
- No se cambia ninguna regla en el camino. No se agregan monedas, filtros ni plazos.
