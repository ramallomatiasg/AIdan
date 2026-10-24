# P17 — deriva post-resultados (PEAD) en acciones de EE.UU. — criterio declarado ANTES de medir

**Fecha:** 24-oct-2026 (rutina semanal, Parte 3: P17 es la primera de la cola). **Tool:**
`tools/backtest_p17_pead.py` (read-only, sin MT5, no toca la DB de AIdan). Baja datos PÚBLICOS a `.cache_p17/`:
fechas de resultados de SEC EDGAR y precios diarios de Yahoo Finance.

## Pregunta

Después de un resultado trimestral que sorprende para bien, el precio sigue subiendo semanas (la información se
difunde lento). arXiv 2512.00280 (2025) reporta ~0,43%/mes de alfa, solo en sorpresas positivas. **¿Comprar tras
una reacción positiva fuerte al resultado y mantener 20 días hábiles deja algo sobre el mercado, neto de costos?**

## Cambio declarado respecto de la propuesta original (por falta de datos, no por mirar resultados)

No existe historial GRATIS de la sorpresa de EPS (estimado vs reportado) para cientos de empresas y 15 años
(la API de Nasdaq da 4 trimestres; Yahoo requiere sesión). Se usa la variante documentada que no la necesita:
**la sorpresa se mide por la reacción del precio al anuncio** (earnings announcement return, EAR; Brandt,
Kishore, Santa-Clara y Venkatachalam 2008, "Earnings announcements are full of surprises"), que reportan una
deriva igual o mayor que la del SUE. Las fechas salen de los **8-K con ítem 2.02** ("Results of Operations") de
EDGAR, con su hora de aceptación ⇒ fechas exactas y sin mirar el futuro.

## Universo y datos

- **Principal:** las 400 primeras empresas (por CIK único, sin duplicar clases de acciones) de
  `sec.gov/files/company_tickers.json` (ordenado por capitalización ACTUAL).
- **Reservados (no se miran salvo que el principal PASE):** las empresas 401-700 de la misma lista.
- Período: eventos de **2010-01-01 a 2026-08-31** (los últimos necesitan 22 días hábiles de precio).
- Precios: cierre ajustado diario de Yahoo; referencia de mercado **SPY**.
- Se descartan eventos sin precio en toda la ventana [d−1, d+22] o con precio < $5.

## Regla (congelada)

- Día del anuncio `d`: si la aceptación del 8-K es antes de las 09:30 ET, `d` = ese día; si es después, el día
  hábil siguiente. (Hora en ET con DST.)
- **EAR** = retorno del cierre de d−1 al cierre de d+1 de la acción, **menos** el de SPY.
- **Señal:** EAR ≥ percentil 80 de los EAR de TODOS los eventos del universo en los 365 días ANTERIORES a d
  (causal; se exigen ≥200 eventos previos, por eso las señales empiezan ~2011).
- **Entrada:** cierre de d+2. **Salida:** cierre de d+22 (20 días hábiles).
- **Resultado por evento:** retorno de la acción − retorno de SPY en esa ventana, **menos 0,10%** (ida y vuelta:
  comisión 0, spread de acciones grandes).

## Control (azar)

Para cada evento con señal: la misma acción, con entrada en un día hábil al azar que no esté a menos de 30 días
de ningún anuncio de esa acción, misma duración y costo. 1.000 réplicas de la media ⇒ **p95 del control**.

## Criterio de PASA (los 5, sobre el universo principal)

1. n ≥ 300 eventos con señal.
2. Media neta > 0 con **CI95 por bootstrap agrupado por mes** cuyo límite inferior > 0.
3. Media neta > 0 en las dos mitades cronológicas.
4. Media neta > **p95 del control**.
5. Media neta > 0 en los eventos de los últimos 3 años (desde 2023-09-01): que el efecto no esté arbitrado hoy.

Descriptivos (no deciden): horizonte 60 días, la cola opuesta (EAR ≤ p20, ¿cae?), por año, y la ganancia anual
de una cartera que reparte el capital entre las posiciones abiertas.

**Si pasa:** correr los reservados (401-700) una vez con la misma regla; si también pasa, shadow en papel (Alpaca
paper) antes de plata. **Si no pasa:** cerrada la deriva post-resultados con esta definición; no se barren el
percentil, la entrada, el horizonte ni el universo.

## Límites

- **Sesgo de supervivencia:** el universo son las grandes de HOY. Las que quebraron o se achicaron no están. Por
  eso el control usa las MISMAS acciones (neutraliza la deriva general de las ganadoras), y el resultado es
  relativo a SPY.
- El ítem 2.02 a veces se presenta por otra cosa que no es el resultado trimestral (correcciones, guías): ruido.
- Datos de Yahoo sin verificar contra otra fuente; spreads reales en small caps no aplican (son grandes).
