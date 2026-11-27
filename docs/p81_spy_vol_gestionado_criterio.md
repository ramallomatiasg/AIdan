# P81 — SPY gestionado por volatilidad, sin apalancamiento: criterio declarado ANTES de medir (26-nov-2026)

**Hipótesis (Moreira & Muir 2017, *JF*):** cuando la volatilidad sube, el retorno esperado del índice no sube en la misma
proporción ⇒ bajar la exposición en los meses volátiles (y tenerla completa en los calmos) mejora el riesgo/retorno
contra tener el índice siempre. Tipo **A** (premio por riesgo, con un componente de flujo: los fondos de vol objetivo
venden cuando la vol sube). Prior bajo: Cederburg, O'Doherty, Wang & Yan (2020) muestran que fuera de muestra muchas
versiones no le ganan al índice. Sin apalancamiento entra con $500.

## Datos (verificado antes de declarar: solo cantidad de días y fechas, **ningún retorno mirado con esta regla**)
- SPY, cierre ajustado diario de Yahoo, 29-ene-1993 → 25-nov-2026 (8.515 días). Cache `.cache_p81/SPY.json`.
- Letra a 3 meses: FRED `DTB3` (cache de P50), último dato disponible hacia atrás, como rendimiento diario /252.

## Regla (fija)
- Al cierre del último día hábil de cada mes m: σ_m = desvío de los últimos 21 retornos diarios en log × √252.
- Exposición del mes siguiente w = min(1, σ* / σ_m); el resto (1 − w) en la letra.
- **σ\*** = media de σ_m de los fines de mes del descubrimiento (ene-1994 → dic-2009). Queda congelada para la reserva.
- Retorno diario = w × r(SPY) + (1 − w) × letra/252. **Costo:** 0,05% × |w nuevo − w viejo| en cada cambio
  (pesimista 0,10%).
- **Comparación:** SPY siempre (la mezcla constante SPY + letra con la misma vol tiene el mismo Sharpe que SPY ⇒ se
  compara el Sharpe). Sharpe = media / desvío del exceso mensual sobre la letra × √12.

## Muestra
- **Descubrimiento:** meses de ene-1994 a dic-2009 (incluye 2000-02 y 2008). **Reserva:** ene-2010 → oct-2026, solo si
  pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Sharpe gestionado − Sharpe de SPY > 0.
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000, los dos con los mismos meses): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Caída máxima del gestionado ≤ caída máxima de SPY.

**Reserva:** criterios 1 y 2.

## Descriptivo (no decide)
Retorno anual, vol, caída máx de los dos; exposición media; rotación por año; por década; la mezcla constante con la
misma vol (retorno a igual riesgo).

## Si PASA
No se activa. Reserva y propuesta al user (regla mensual, un ETF, automatizable con un broker de comisión cero).
## Si NO PASA
Cerrado el manejo por volatilidad en el índice; no se prueban otras ventanas (63 días), otros objetivos de vol,
apalancamiento, ni otros ETFs.
