# P12 — drift pre-FOMC (Lucca & Moench 2015) en índices — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "probá lo restante así nos sacamos las dudas"). **Tool:**
`tools/backtest_p12_pre_fomc.py` (read-only, sin MT5, no toca la DB). Lee `.cache_p1/M15`.

## Pregunta

Lucca y Moench (2015) documentan que el S&P 500 sube en promedio en las 24 h previas al anuncio de la Fed
(14:00 ET del día anterior → justo antes del comunicado), con todo el exceso de retorno de la bolsa de esos años
concentrado ahí. La literatura posterior dice que se debilitó después de publicarse ⇒ **prior bajo**. ¿Está en
2020-2026, en los índices de esta cuenta?

## Eventos (congelados)

Las reuniones PROGRAMADAS con comunicado, desde que hay data (USTEC desde 2020-06-01, US30 desde 2020-05-29) hasta
el fin del cache (2026-10-09). Fechas del comunicado:
2020: 06-10, 07-29, 09-16, 11-05, 12-16 · 2021: 01-27, 03-17, 04-28, 06-16, 07-28, 09-22, 11-03, 12-15 ·
2022: 01-26, 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14 · 2023: 02-01, 03-22, 05-03, 06-14, 07-26, 09-20,
11-01, 12-13 · 2024: 01-31, 03-20, 05-01, 06-12, 07-31, 09-18, 11-07, 12-18 · 2025: 01-29, 03-19, 05-07, 06-18,
07-30, 09-17, 10-29, 12-10 · 2026: 01-28, 03-18, 04-29, 06-17, 07-29, 09-16. (Sin reuniones de emergencia.)

## Trade (congelado)

- **Largo** en la apertura de la vela M15 de las **21:00 server (= 14:00 ET)** del día hábil anterior al comunicado.
- **Salida** en la apertura de la vela de las **20:45 server (= 13:45 ET)** del día del comunicado (15 min antes).
  Server = NY + 7 h todo el año (verificado en P3).
- Si falta alguna de las dos velas, el evento se descarta (se cuenta).

## Costos

Spread de la vela de entrada y de la de salida (mínimo de la barra ⇒ cota optimista). Índices sin comisión.
Financiación por la noche cruzada: **0,02% del precio** por trade (≈ tasa + 2-3% anual / 360, cota alta del
período). Métrica: neto en % del precio.

## Control

La misma ventana (21:00 server del día anterior → 20:45 server del día) en **todos los días hábiles que NO son
comunicado**. 5.000 réplicas: media de n días al azar de ese conjunto (n = eventos del instrumento).

## Criterio de PASA (los 5, principal = pool USTEC + US30 por evento)

1. n ≥ 35 eventos por instrumento.
2. Media neta del pool > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control en los dos instrumentos.
5. USTEC y US30 los dos con media neta > 0.

DE40, XAUUSD y EURUSD se reportan como descriptivos (no deciden).

**Si pasa:** no hay reservados para este efecto ⇒ se propone directo como **shadow en vivo** (registrar el trade en
papel en cada FOMC), y se lee a n=8 reuniones (~1 año) antes de operar en demo.
**Si no pasa:** cerrado el drift pre-FOMC sobre esta data; no se barren ventanas ni instrumentos.

## Límites

n chico por construcción (~48 reuniones). Spread de la vela = cota optimista. 2020-26 fue un período alcista en
índices ⇒ por eso el control es la misma ventana en días normales, no cero.
