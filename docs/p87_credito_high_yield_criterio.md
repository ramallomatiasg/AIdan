# P87 — Premio de crédito high yield contra Tesoro (VWEHX − VFITX): criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis:** los bonos de empresas con riesgo de quiebra pagan, en promedio, más de lo que se pierde por quiebras
(premio de crédito). Tipo **A** (premio por riesgo). Riesgo conocido: se parece a tener acciones (cae en 2008 y 2020)
⇒ además de que exista, se pide que no sea solo "un poco de índice".

## Datos (verificado antes de declarar: solo filas y fechas, **ningún retorno mirado con esta regla**)
- VWEHX (Vanguard High-Yield Corporate, desde 1980), VFITX (Vanguard Intermediate-Term Treasury, desde 28-oct-1991),
  VFINX (Vanguard 500, para el alfa): cierre ajustado diario de Yahoo hasta 25-nov-2026. Cache `.cache_p87/`.
- Letra a 3 meses: FRED `DTB3` (cache de P50), /252 por día.
- Los retornos del fondo ya vienen netos de su comisión. Comprar y mantener: costo 0,05% de entrada y de salida
  (despreciable, se reporta).

## Muestra
- Retornos mensuales de fin de mes a fin de mes. **Descubrimiento:** ene-1992 → dic-2008 (incluye 2001-02 y 2008).
  **Reserva:** ene-2009 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 4)
1. Exceso medio mensual VWEHX − VFITX > 0.
2. CI95 de ese exceso medio por bootstrap en bloques de 6 meses (5000): inferior > 0.
3. Exceso medio > 0 en las dos mitades cronológicas.
4. Alfa > 0 en la regresión mensual (VWEHX − letra) = α + b₁(VFINX − letra) + b₂(VFITX − letra): que quede algo después
   de descontar el índice y el Tesoro.

**Reserva:** criterios 1 y 2.

## Descriptivo (no decide)
Exceso anual, Sharpe del exceso, caída máx del exceso y de VWEHX, correlación con VFINX, betas b₁ y b₂, por década.

## Si PASA
No se activa. Reserva y propuesta (ETF HY contra ETF de Tesoro, con la comisión del ETF) + correlación con la cartera de
lo que pasa.
## Si NO PASA
Cerrado el premio de crédito high yield por fondos; no se prueban otros fondos, plazos, ni filtros de spread.
