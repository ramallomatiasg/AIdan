# P82 — Tendencia de 12 meses multi-activo con ETFs: criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017):** el activo que rindió más que la letra en
los últimos 12 meses tiende a seguir rindiendo más el mes siguiente ⇒ tener cada activo solo cuando su tendencia de 12
meses es positiva mejora el riesgo/retorno contra tenerlos siempre. Tipo **A** (premio por riesgo / flujos lentos).
En AIdan solo se midió semanal en FX (E4) y en cripto (P40); multi-activo mensual con ETFs, nunca. Sin apalancamiento,
entra con $500 (fracciones).

## Datos (verificado antes de declarar: solo cantidad de días y fechas, **ningún retorno mirado**)
- Cierre ajustado diario de Yahoo (`.cache_p82/`): SPY (1993), EFA (ago-2001), EEM (abr-2003), TLT e IEF (jul-2002),
  GLD (nov-2004), VNQ (sep-2004), DBC (feb-2006), todos hasta 27-nov-2026.
- Letra a 3 meses: FRED `DTB3` (cache de P50), último dato disponible hacia atrás, rendimiento diario /252.

## Regla (fija)
- Al cierre del último día hábil de cada mes m, para cada ETF i: R12_i = retorno total de los últimos 12 fines de mes;
  L12 = retorno compuesto de la letra en el mismo lapso.
- Mes siguiente: peso 1/8 en el ETF i si R12_i > L12; si no, ese 1/8 va a la letra. Sin apalancamiento, sin cortos.
- **Comparación:** 1/8 en cada ETF siempre, rebalanceado a pesos iguales cada fin de mes.
- **Costo:** 0,05% × rotación (suma de |Δpeso| de cada fin de mes, contra los pesos que dejó el mes) en los dos
  (pesimista 0,10%).
- Sharpe = media / desvío del exceso mensual sobre la letra × √12.

## Muestra
- Primer mes con los 8 ETFs con 12 meses de historia: decide el fin de feb-2007 ⇒ **descubrimiento mar-2007 →
  dic-2015** (incluye 2008). **Reserva:** ene-2016 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 6)
1. Sharpe tendencia − Sharpe del 1/8 siempre > 0.
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000, los dos con los mismos meses): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Caída máxima de la tendencia ≤ caída máxima del 1/8 siempre.
6. **Control al azar:** 1000 carteras que tienen cada ETF en cada mes con probabilidad igual a la fracción de meses en
   que la regla lo tuvo (mismo costo): Sharpe de la tendencia > percentil 95 del azar.

**Reserva:** criterios 1, 2 y 6.

## Descriptivo (no decide)
Retorno anual, vol, caída máx; exposición media; rotación por año; por año calendario; cuál ETF aporta.

## Si PASA
No se activa. Reserva y propuesta al user (regla mensual fija, 8 ETFs, broker de comisión cero).
## Si NO PASA
Cerrado: no se prueban otras ventanas (3/6/9 meses), otra lista de ETFs, pesos por volatilidad ni apalancamiento.
