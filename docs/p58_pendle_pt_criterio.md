# P58 — Rendimiento FIJO de Pendle (comprar PT de stablecoins y aguantar al vencimiento) contra la letra: criterio declarado ANTES de medir (18-nov-2026)

**Hipótesis:** el PT de Pendle se compra con descuento y paga 1 unidad del activo al vencimiento ⇒ el rendimiento queda
fijo al entrar. Paga más que la letra porque cobra riesgo de contrato y del subyacente. Tipo **A** (premio por riesgo).
Capital chico, automatizable. Nunca medido acá.

## Datos (verificado antes de declarar: listas de mercados y fechas, **sin precios históricos mirados**)
- La serie de DefiLlama solo tiene los pools VIVOS (sesgo de supervivencia) ⇒ se usa la API pública de Pendle:
  `core/v1/{chain}/markets?is_expired=true` en las 13 cadenas (757 mercados vencidos, cache
  `.cache_p58/expired_markets.json`, bajado el 18-nov). Incluye los que salieron mal. *Aviso honesto:* al inspeccionar el
  formato vi el precio ACTUAL de un solo mercado (msUSD ~0,81, un subyacente que se despegó); no se miró nada más.
- **Mercados de stablecoin** (regla fija): símbolo del `accountingAsset` contiene `USD`, `DAI` o `GHO` ⇒ 368 mercados
  (2024: 36, 2025: ~158, 2026: ~174).
- Precio diario del PT en USD: `core/v4/{chain}/prices/{pt}/ohlcv?time_frame=day`; TVL diario:
  `core/v2/{chain}/markets/{market}/historical-data?time_frame=day`. Cache `.cache_p58/`.
- Letra a 3 meses: FRED `DTB3` (cache de P50).

## Regla
- **Entrada:** close del PT en USD el día `max(alta del mercado + 7 días, vencimiento − 90 días)`. Hace falta TVL ≥ $1 M
  ese día y ≥ 30 días hasta el vencimiento; si no, el mercado no entra (se cuenta).
- **Salida:** close del PT en USD el día del vencimiento (después del vencimiento el PT vale lo que vale el subyacente
  en USD ⇒ un depeg o un default aparece acá). Si no hay precio ese día, el último close disponible hasta 5 días antes;
  si tampoco, el mercado se descarta y se cuenta.
- **Costo:** gas $5 + deslizamiento 0,1% sobre una posición de $1.000 ⇒ **0,6% por posición**. Pesimista: **1,2%**.
- Exceso del mercado = (P_salida / P_entrada − 1 − costo) − DTB3 media × días / 365.
- Agregado: premio anualizado = Σ exceso / Σ días × 365 (igual peso por mercado).

## Muestra
- **Descubrimiento:** vencimientos hasta el 30-jun-2025. **Reserva:** 1-jul-2025 → 18-nov-2026, solo si pasa.
- Los mercados que vencen el mismo mes comparten riesgo ⇒ CI por bootstrap agrupado por **mes de vencimiento**.

## Criterios (descubrimiento; PASA = los 5)
1. n ≥ 25 mercados.
2. Premio anualizado > 0 y extremo inferior del CI95 agrupado > 0 (5000 remuestreos).
3. Las dos mitades cronológicas > 0.
4. Premio anualizado > 0 con el costo pesimista.
5. Ningún mes de vencimiento con resultado medio (igual peso, sin anualizar) < −5%.

**Reserva:** premio anualizado > 0, CI inferior > 0 y criterio 5 (incluye las caídas de stablecoins de fines de 2025).

## Descriptivo (no decide)
Rendimiento implícito medio al entrar, peor mercado (subyacente y pérdida), cuántos terminaron < 0,98 de lo esperado,
por cadena, por año.

## Límites
- El precio diario del PT en USD es el de Pendle (puede no ser ejecutable con TVL chica: por eso el piso de $1 M).
- Riesgo de contrato de Pendle no modelado más allá de lo que muestre el precio.
- El user no compra letras: la letra es la vara de la tasa libre.

## Si PASA
No se activa. Reserva; después papel (cartera de PT en vivo) con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrado Pendle PT de stablecoins; no se buscan otras entradas, pisos de TVL, cadenas ni activos.
