# P2 — trend following clásico (canal Donchian / turtle) en D1 y H4 — criterio declarado ANTES de medir

**Fecha:** 16-oct-2026 (rutina semanal). **Tool:** `tools/backtest_p2_donchian.py` (read-only, sin MT5,
no toca la DB). Lee `.cache_fase2/M5_500000` (FX) y `.cache_p1/M15` (oro/índices).

## Pregunta

Todo lo intradía medido (Fases 2-6, P1) pierde contra el costo. El costo relativo cae 10x en D1 (screen
9-oct: EURUSD ~1,5% del ATR D1 contra ~15% del rango M15). H4 solo se probó con el detector de
`structure`; un sistema de tendencia clásico nunca. **¿El turtle clásico tiene edge neto en FX?**

## Reglas (congeladas)

- **Barras de señal:** D1 (día del server) y H4, re-muestreadas desde M5 (FX) / M15 (oro, índices).
  Días con <50% de las barras esperadas (domingos parciales) se descartan.
- **Entrada:** cierre > máximo de los N altos ANTERIORES ⇒ largo; cierre < mínimo de los N bajos
  anteriores ⇒ corto. Una posición por instrumento a la vez, sin pirámide, sin filtro de "última
  señal perdedora".
- **Ejecución:** apertura de la primera vela M5/M15 posterior al cierre de la barra de señal; si cae en
  [23:00, 01:00) server (rollover, spread ancho), se corre a la primera vela ≥ 01:00. Lección de Fase 4.
- **Stop inicial:** 2·ATR(20) del precio de entrada (ATR = media simple del true range de 20 barras de
  señal). Se chequea en cada vela fina; si la vela abre más allá del stop, se llena a la apertura.
- **Salida por canal (trailing):** cierre de la barra de señal < mínimo de los M bajos anteriores (largo)
  / > máximo de los M altos (corto) ⇒ salida con la misma regla de ejecución.
- **Sistemas:** **principal = D1, N=20 / M=10.** Secundarios descriptivos: D1 55/20, H4 20/10, H4 55/20.

## Costos

Comisión del spec (Raw, round-turn) + spread de la vela fina de entrada Y de salida (mínimo de la barra
⇒ cota OPTIMISTA, piso 0,1p en FX igual que P1) + **swap real del spec** por noche cruzada (miércoles
×3, sáb/dom 0, misma función que Fase 3b). Oro/índices: el cache no trae swap ⇒ se reportan netos SIN
swap más el swap por noche que los llevaría a cero (descriptivo, no puntúan el gate).

## Métrica

Neto por trade en **R** (1R = distancia del stop inicial en pips), para poder juntar pares. Se reporta
también en pips.

## Criterio de PASA (los 5, sobre el principal, pool de los 20 pares de Fase 1)

1. n ≥ 300 trades.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 200 réplicas con entradas al azar (mismo número de entradas por par,
   dirección al azar, mismas reglas de salida y costos).
5. ≥ 12 de 20 pares con media neta > 0.

**Si pasa:** correr los 6 reservados (`RESERVADOS`) una sola vez con la misma regla. **Si no pasa:** los
reservados no se miran, y se cierra "turtle D1/H4 en FX" sobre esta data (no barrer N/M/stop).
Los secundarios no rescatan al principal: si solo pasa un secundario, se registra como hipótesis a
re-declarar, no como PASA.

**Límite conocido de cuenta:** con SL de ~2·ATR D1 (≈110p en EURUSD) el lote mínimo 0,01 arriesga ~$11
= ~1,8% de $600. Si pasa, la ejecución en vivo choca con el lote mínimo igual que el D1 (decisión de
cuenta, no de código).
