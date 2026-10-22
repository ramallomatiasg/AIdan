# P10 — fade del canal Donchian D1 (reversión de mediano plazo) — criterio declarado ANTES de medir

**Fecha:** 22-oct-2026 (rutina semanal). **Tool:** `tools/backtest_p10_fade_donchian.py` (read-only, sin MT5,
no toca la DB). Reusa las piezas de `tools/backtest_p2_donchian.py` (importadas, no copiadas) sobre
`.cache_fase2/M5_500000`.

## Pregunta

P2 (16-oct) dio que entrar CON la ruptura de 20 días en FX es **peor que el azar** (−0,226R, control
mediana −0,14R, 16/20 pares negativos, las dos mitades) con un costo de solo 0,016R ⇒ el bruto negativo
es información, no fricción. **¿Operar al revés (vender la ruptura del máximo de 20 días, comprar la del
mínimo) tiene edge neto fuera de muestra?**

Como la idea sale de mirar los 20 pares de P2, **se mide únicamente en los 6 pares reservados**
(`RESERVADOS` de `screen_generators.py`: CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD), nunca mirados
por ninguna fase. Data: los 6 tienen M5 completo 2019-12-04 → 2026-08-18.

## Reglas (congeladas)

Todo idéntico a P2 principal (D1, N=20, M=10) salvo la dirección:

- **Señal:** cierre D1 > máximo de los 20 altos anteriores ⇒ **CORTO**; cierre < mínimo de los 20 bajos
  anteriores ⇒ **LARGO**.
- **Ejecución:** apertura de la primera vela M5 posterior al cierre de la barra, corrida fuera de
  [23:00, 01:00) server (igual que P2).
- **Stop:** 2·ATR(20) D1 en contra del fade (por encima de la entrada en el corto), chequeado vela M5 por
  vela M5, gap ⇒ apertura.
- **Salida (objetivo):** la salida por canal de la posición de P2 que se está fadeando. El corto (nacido de
  una ruptura alcista) sale cuando el cierre D1 < mínimo de los 10 bajos anteriores; el largo, cuando el
  cierre D1 > máximo de los 10 altos anteriores. Es decir: el fade vive exactamente lo que viviría el
  trade de P2, con el stop del otro lado.
- Una posición por par, sin pirámide. Sin secundarios (ni D1 55/20 ni H4): una sola variante.

## Costos

Los de P2: comisión Raw del spec + spread de la vela de entrada y de salida (piso 0,1p) + swap real del
spec por noche (miércoles ×3). *Límite conocido:* el swap del spec es el ACTUAL, aplicado a todo el
período (igual que P2).

## Métrica

Neto por trade en R (1R = stop inicial).

## Criterio de PASA (los 5, pool de los 6 reservados)

1. n ≥ 150 trades.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 200 réplicas con entradas al azar (mismo número de entradas por par,
   dirección al azar, mismas reglas de stop/salida y costos).
5. ≥ 4 de 6 pares con media neta > 0.

**Una sola corrida.** El tool se niega a re-correr los reservados si ya existe el resultado. No se
barren N/M/stop/salida después de verlo.

**Descriptivo (no puntúa, no rescata):** el mismo fade sobre los 20 pares de P2 (in-sample, de donde nació
la idea) para verificar que la implementación es el espejo de P2.

**Si pasa:** hipótesis para shadow en EURUSD D1 (junto/en lugar del track D1), con el mismo choque de lote
mínimo que P2 (SL ≈ 2·ATR D1 ≈ 110p ⇒ ~1,8% de $600 con 0,01): decisión de cuenta, no de código.
**Si no pasa:** se cierra "Donchian D1 en FX, en cualquier dirección" sobre esta data.
