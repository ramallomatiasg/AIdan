# Fase 3b — A1 (reversión a 2σ) por el arnés completo · criterio declarado ANTES de correr

**Fecha: 22 Sep 2026.** Commiteado antes de escribir el tool y antes de ver un solo número.

## Por qué

Fase 3 (`24affcb`, criterio `12622b3`): de 9 generadores congelados, solo **A1** pasó el screen
(close medio +0,982p a H96 vs 0,90 de costo, > p99 del azar, n=942k, 20 pares, M5). Y el screen
declaraba que pasarlo NO habilita a operar: habilita "el arnés completo de Fase 2 (costos reales,
swap, 4 sesiones, dos mitades, control p95) y después los 6 pares reservados". Fase 2b (`1363467`)
dejó a la reversión como la única línea con evidencia a favor. El user pidió correrlo (22-sep).

Las 4 cautelas del screen que esta corrida tiene que resolver: (a) el edge neto era ~+0,08p, al
borde; (b) H96 = 8 h cruza rollover ⇒ **swap**, que el screen excluyó; (c) 942k señales con hold
de 8 h = solapamiento masivo, "tomar todas" no es implementable; (d) el screen no cobró **spread**.

## Qué se mide (congelado)

- **Señal**: A1 tal cual el doc de Fase 3 y `tools/screen_generators.py:gen_A1` — MA(20) y desvío
  poblacional(20) del close; `z > +2` ⇒ PUT, `z < −2` ⇒ CALL; entrada al close de la vela señal.
- **Universo**: los mismos **20 pares de Fase 1** del screen, M5, cache `.cache_fase2/M5_500000`
  (15 con 6,7 años; USDCAD, AUDJPY, AUDNZD, AUDCAD y CADJPY con 1,6). Los **6 reservados**
  (CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD) **NO se miran** salvo que pase en los 20.
- **Implementable**: **una posición por par a la vez**. Mientras hay posición abierta en un par, las
  señales de ese par se ignoran. (Resuelve (c).)
- **Salida**: por tiempo a **H96** (96 velas M5 = 8 h de mercado), sin SL ni TP — el mismo
  horizonte y la misma medida que pasaron el screen. H12 y H48 se reportan como **secundarios**,
  no deciden. No se prueban otras salidas en esta corrida.
- **Costos (resuelve (b) y (d))**, en pips, por trade:
  - comisión round-turn del par (`spec.commission_pips`, del broker);
  - **spread de la vela de entrada** (campo `spread` de MT5, en points ⇒ /10 pips). Ojo: MT5
    guarda el spread MÍNIMO de la barra ⇒ es una **cota optimista** del costo (EURUSD da mediana 0);
  - **swap real**: por cada rollover (00:00 hora del server) cruzado entre entrada y salida, el
    swap del lado (`swap_long/short_pips` del broker, snapshot del 18-ago); la noche de
    **miércoles cobra triple**; las noches de sábado y domingo no cobran.
- **Sesión** de la entrada, por hora UTC (server = UTC+3 con horario de verano de EE.UU., UTC+2 sin
  él): london 7-12, overlap 12-16, ny 16-20, off el resto.

## Criterio — tiene que cumplir TODO sobre los 20 pares

1. media neta por trade **> 0**
2. **CI95 bootstrap** de la media neta, límite inferior **> 0**
3. media neta **> 0 en las dos mitades** del período (corte por fecha)
4. media neta **> percentil 95** del control aleatorio (200 reps; mismo n por par, mismo ratio
   long/short por par, misma salida a H96, mismos costos incluidos spread y swap)
5. media neta **> 0 en cada una de las 4 sesiones** de entrada

**Si pasa** ⇒ se corre lo mismo sobre los 6 reservados; pasa el out-of-sample si allí la media neta
es **> 0 y > p95 del control**. Solo con las dos cosas se propone construirlo en **shadow** en vivo
(nunca directo a operar).
**Si no pasa** ⇒ la reversión a 2σ queda refutada con costos reales y se documenta como cerrada;
no se buscan variantes (otro umbral, otra media, otro horizonte) sobre esta misma data: eso sería
fabricar el falso positivo que Fase 3 declaró que iba a evitar.

## Límites

Sin slippage; swap con el snapshot del 18-ago (cambia en el tiempo); spread de la vela = el del
momento de la barra, no el del instante exacto; los 4 pares con 1,6 años aportan solo a la mitad
reciente. Un "pasa" es permiso para shadow, no para operar.
