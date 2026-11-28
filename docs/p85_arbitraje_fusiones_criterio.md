# P85 — Arbitraje de fusiones con ETF (MNA) contra la letra: criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis (Mitchell & Pulvino 2001; Baker & Savasoglu 2002):** el que compra la acción de la empresa que va a ser
comprada cobra un premio por cargar el riesgo de que la fusión se caiga (~4%/año sobre la tasa libre en los papers,
poco correlacionado con el índice salvo en crisis). Tipo **A** (premio por riesgo). Es un motor fuera de cripto, que es
lo que la cartera de lo que pasa necesita. Entra con $500, sin reglas (comprar y mantener).
Riesgo: el ETF cobra ~0,75%/año (ya incluido en el precio) y el premio publicado se achicó.

## Datos (verificado antes de declarar: solo cantidad de días y fechas, **ningún retorno mirado**)
- MNA (IQ Merger Arbitrage ETF), cierre ajustado diario de Yahoo, 17-nov-2009 → 27-nov-2026 (`.cache_p85/`).
- SPY ajustado de Yahoo (`.cache_p85/`), solo para correlación y alfa.
- Letra a 3 meses: FRED `DTB3` (cache de P50), último dato disponible hacia atrás, rendimiento diario /252.

## Regla (fija)
- Retornos mensuales (último día hábil de cada mes) de MNA, SPY y la letra. Exceso = MNA − letra.
- **Costo:** 0,05% a la entrada y 0,05% a la salida del período (pesimista 0,10% c/u).

## Muestra
- **Descubrimiento:** ene-2010 → dic-2017. **Reserva:** ene-2018 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Exceso anual compuesto sobre la letra > 0 (con costo).
2. CI95 del exceso medio mensual por bootstrap en bloques de 6 meses (5000): inferior > 0.
3. Exceso > 0 en las dos mitades cronológicas.
4. **Alfa** (intercepto de la regresión del exceso mensual de MNA sobre el exceso de SPY) > 0: que no sea solo un poco de
   índice.
5. Correlación mensual con SPY ≤ 0,7 (que diversifique).

**Reserva:** criterios 1, 2 y 4.

## Descriptivo (no decide)
Sharpe del exceso, vol, caída máx, beta con SPY, peor año; correlación con el carry de funding (P15/P19) si los meses se
alinean.

## Si PASA
No se activa. Reserva, entra a `docs/cartera_de_lo_que_pasa.md` y propuesta al user.
## Si NO PASA
Cerrado el arbitraje de fusiones por ETF; no se prueban otros fondos (MERFX, ARBFX), ni filtros de cuándo tenerlo.
