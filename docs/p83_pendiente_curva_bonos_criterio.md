# P83 — Pendiente de la curva del Tesoro → bonos largos: criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis (Fama & Bliss 1987; Campbell & Shiller 1991; Cochrane & Piazzesi 2005):** cuando la curva está empinada, el
premio por plazo esperado de los bonos largos es mayor ⇒ tener bonos largos solo cuando la pendiente es alta (y la letra
cuando es baja) mejora el riesgo/retorno contra tenerlos siempre. Tipo **A** (prima por plazo). Nunca medido en AIdan.
Automatizable con un ETF (TLT/VGLT). Prior medio-bajo: la pendiente se refleja rápido en el precio.

## Datos (verificado antes de declarar: solo cantidad de días y fechas, **ningún retorno mirado**)
- VUSTX (Vanguard Long-Term Treasury), cierre ajustado diario de Yahoo, 19-may-1986 → 25-nov-2026 (`.cache_p83/`).
- Pendiente: FRED `T10Y3M` (10 años − 3 meses), diaria desde 1982 (`.cache_p83/`).
- Letra a 3 meses: FRED `DTB3` (cache de P50), último dato disponible hacia atrás, rendimiento diario /252.

## Regla (fija)
- Al cierre del último día hábil de cada mes m: S_m = último valor de `T10Y3M` publicado hasta ese día.
- Mes siguiente: 100% VUSTX si S_m > **S\***, si no 100% letra.
- **S\*** = mediana de S_m en los fines de mes que deciden los meses del descubrimiento (dic-1986 → nov-2005).
  Congelada para la reserva.
- **Costo:** 0,05% en cada cambio de posición (pesimista 0,10%).
- **Comparación:** VUSTX siempre. Sharpe = media / desvío del exceso mensual sobre la letra × √12.

## Muestra
- **Descubrimiento:** ene-1987 → dic-2005. **Reserva:** ene-2006 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 6)
1. Sharpe regla − Sharpe de VUSTX > 0.
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Exceso medio sobre la letra en los meses DENTRO > exceso medio de VUSTX en los meses FUERA (la señal separa).
6. **Control al azar:** 1000 reglas que están dentro cada mes con la misma probabilidad que la regla (mismo costo
   por cambio): Sharpe de la regla > percentil 95 del azar.

**Reserva:** criterios 1, 2 y 6.

## Descriptivo (no decide)
Retorno anual, vol, caída máx de los dos; fracción de meses dentro; cambios por año; por década.

## Si PASA
No se activa. Reserva y propuesta al user.
## Si NO PASA
Cerrado: no se prueban otros umbrales (cuantiles, media móvil), otras pendientes (10−2, 30−3), ni otros plazos de bono.
