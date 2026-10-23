# P6 — volumen de ticks como filtro de la ruptura de `structure` — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "probá lo restante"). **Tool:** `tools/backtest_p6_volumen.py`
(read-only, sin MT5, no toca la DB). Lee los checkpoints de Fase 2 (`.cache_fase2/M15_500000/ckpt`,
`v1_M15_live_<par>_london.pkl`: cada trade del detector con su hora y su neto ya calculado con costos) y las
velas M15 del mismo cache (columna `tick_volume`).

## Pregunta

Backlog #4 desde mayo: una ruptura con pico de volumen sería más confiable que una sin volumen. `structure` es
peor que el azar en general (Fase 2, P1). **¿El subconjunto con pico de volumen en la vela de la señal tiene neto
positivo, y es mejor que elegir el mismo número de señales al azar?** Prior bajo: un filtro solo puede recortar.

## Definición (congelada)

- Universo: las señales de `structure` en M15, perfil vivo (SL 15 / TP 60 / 3 velas), sesión `london`, 20 pares
  de Fase 1 — exactamente las que midió Fase 2, con su neto (comisión + swap) ya calculado.
- `vol_ratio = tick_volume[i] / mediana(tick_volume[i−20 .. i−1])`, con `i` = vela de la señal (cerrada, sin
  mirar el futuro).
- **Pico = `vol_ratio ≥ 1,5`.** Principal = las señales con pico.
- Descriptivo: terciles de `vol_ratio` y la diferencia pico vs sin pico.

## Criterio de PASA (los 5, pool de los 20 pares, señales con pico)

1. n ≥ 1.000.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 2.000 subconjuntos al azar de las MISMAS señales, con el mismo n por par
   (responde si el volumen elige mejor que el azar).
5. ≥ 12 de 20 pares con media neta > 0.

**Si pasa:** los 6 reservados con el mismo tool, una vez. **Si no pasa:** cerrado el filtro de volumen sobre
`structure`; no se barre el umbral.

## Límites

`tick_volume` de MT5 es cantidad de cambios de precio, no volumen real (proxy). El neto de Fase 2 usa la comisión
y el swap del spec; el spread no se cobró en Fase 2 ⇒ el neto es una cota OPTIMISTA (si no pasa así, menos con
spread).

**Enmienda 1 (23-oct, ANTES de ver un número):** Fase 2 en M15 solo tiene checkpoints para **15** de los 20 pares
(USDCAD, AUDJPY, AUDNZD, AUDCAD y CADJPY arrancan en 2025 y no entraron). El universo pasa a esos 15 y el
criterio 5 a **≥ 9 de 15** (el mismo 60%). Nada más cambia.
