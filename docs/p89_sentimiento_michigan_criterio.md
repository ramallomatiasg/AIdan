# P89 — Sentimiento del consumidor (Michigan) contrario → S&P 500: criterio declarado ANTES de medir (28-nov-2026)

**Hipótesis (Fisher & Statman 2003; Lemmon & Portniaguina 2006):** con el sentimiento del consumidor en el piso, el
índice rinde más el mes siguiente (pesimismo exagerado que revierte) ⇒ estar en el S&P 500 solo en esos meses (y en la
letra el resto) mejora el riesgo/retorno contra tener el índice siempre. Tipo **C** (información: una encuesta, no el
precio). Reemplazo de P84 (AAII sin datos). Prior bajo: puede ser solo "comprar después de caídas".

## Datos (verificado antes de declarar: solo fechas y cantidad de filas, **ningún retorno mirado**)
- FRED `UMCSENT` (`.cache_p89/UMCSENT.json`): trimestral 1952-1977, **mensual desde ene-1978** → oct-2026. Se usa solo
  la serie mensual (desde 1978-01).
- VFINX (Vanguard 500, cierre ajustado diario de Yahoo, 2-ene-1980 → 25-nov-2026, `.cache_p89/VFINX.json`).
- Letra: FRED `DTB3` (cache de P50), último dato hacia atrás, /252 por día.

## Regla (fija)
- Al cierre del último día hábil de cada mes m: U = valor de `UMCSENT` del mes **m−1** (el del mes m sale definitivo
  recién a fin de mes; usar m−1 garantiza que ya estaba publicado).
- Percentil de U contra los valores mensuales **anteriores** (hasta 120 = 10 años; con menos historia desde 1978, mínimo
  36). Si U está en el **20% más bajo** (fracción de valores previos ≤ U es ≤ 0,20) ⇒ mes siguiente 100% VFINX; si no,
  100% letra.
- **Costo:** 0,05% por cambio (pesimista 0,10%). Sharpe = media/desvío del exceso mensual sobre la letra × √12.
- **Comparación:** VFINX siempre.

## Muestra
- **Descubrimiento:** mar-1981 → dic-2002 (primer mes con 36 valores previos). **Reserva:** ene-2003 → oct-2026, solo si
  pasa.

## Criterios (descubrimiento; PASA = los 6)
1. Sharpe regla − Sharpe VFINX > 0.
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Exceso medio de VFINX sobre la letra en los meses DENTRO > en los meses FUERA (la señal separa).
6. **Control al azar:** 1000 reglas dentro cada mes con la misma probabilidad que la regla (mismo costo): Sharpe de la
   regla > percentil 95 del azar.

**Reserva:** criterios 1, 2 y 6.

## Descriptivo (no decide)
Fracción de meses dentro, cambios por año, anual/vol/caída máx de las dos, por década, y exceso dentro/fuera.

## Si PASA
No se activa. Reserva y propuesta al user (ETF del S&P 500, entra con $500).
## Si NO PASA
Cerrado el sentimiento de Michigan como señal del índice: no se prueban otros cuantiles, ventanas, la versión "alto ⇒
salir", ni la sub-serie de expectativas.
