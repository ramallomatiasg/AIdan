# Fase 2b — ¿el "peor que el azar" era la IDEA o un BUG de cálculo? (criterio declarado ANTES de correr)

**Fecha: 22 Sep 2026.** Commiteado antes de ver un solo número de la variante corregida.

## Por qué existe

Estudio de primeros principios de `detect_structure_signals` (pedido del user: *"ver si la lógica
o el cálculo que hace AIdan es la correcta, no comparar decisiones malas contra muchos años"*).
Encontró un error de cálculo:

- El detector se escribió en marzo (`ff68330`, `f3f53b7`) asumiendo que `candles[-1]` es la vela
  **en formación**: `price` = precio vivo, `prev1 = candles[-2]` = "última vela cerrada",
  `recent_candles = candles[-6:-1]` = "últimas 5 cerradas".
- El 17-abr (`863972b`, v3.6.0) `price_feed._fetch_mt5` empezó a **descartar** la vela en
  formación. Verificado 22-sep contra MT5: la condición siempre es verdadera (el `time` de MT5 está
  en hora del server, adelantado respecto de UTC), así que la vela en formación se descarta siempre.
- Desde entonces `price` = cierre de la última vela cerrada y `prev1` = la **anterior** a esa ⇒
  una ruptura exige **2 cierres** del otro lado del nivel en vez de 1 y dispara **una vela tarde**
  (5 min en M5, 15 en M15, 1 h en H1). El momentum usa como "vela de expansión" la penúltima, el
  filtro de mecha mira la penúltima, etc.
- El arnés de Fase 2 (`tools/backtest_fase2.py`) le pasa al detector ventanas que terminan en una
  vela CERRADA ⇒ **midió el detector con el desfase**. El veredicto del 18-ago ("peor que el azar")
  juzga la implementación, no necesariamente la idea.

## Qué se cambia (y nada más)

Variante `lagfix`: el MISMO `technical.py`, con 4 índices corridos una posición, aplicado como
transformación del fuente en memoria (producción no se toca; cada reemplazo tiene que matchear
exactamente 1 vez o la corrida aborta):

| línea | original | lagfix |
|---|---|---|
| `prev1` | `candles[-2]` | `candles[-1]` |
| `prev2` | `candles[-3]` | `candles[-2]` |
| `recent_candles` | `candles[-6:-1]` | `candles[-5:]` |
| `consol_candles` (momentum) | `candles[-8:-2]` | `candles[-7:-1]` |

`price` no cambia: el cierre de la última vela cerrada ES el precio al momento de decidir (arranque
de la vela siguiente), que es lo que el diseño quería. El cruce de medias (`candles[:-1]`) ya era
correcto y no se toca.

## Qué se corre

Idéntico al primario de Fase 2: M15, perfil `live` (SL 15 / TP 60 / hold 3 / min_conf 60),
params `live` (sin cambios desde el 30-jul, verificado), 21 pares, las 4 sesiones, mismo control
aleatorio (200 reps), mismos costos, mismas 4 condiciones de `docs/fase2_criterio_declarado.md`.
**Control de reproducibilidad:** antes de comparar se recalcula con el código de hoy al menos un job
de la variante original y tiene que dar el mismo `n` y la misma media que el checkpoint del 18-ago;
si no, la base no es comparable y se recalcula entera.

## Cómo se lee (fijado ahora)

Por sesión se reportan 3 números: `original` (18-ago), `lagfix`, `control` (mediana y p95).

1. **`lagfix` PASA las 4 condiciones en las 4 sesiones** ⇒ la idea tenía edge y el bug lo
   escondía. Se propone el fix en vivo (con OK del user, rebuild en sábado) y se re-mide forward.
   Un PASA sigue siendo permiso para investigar, no para escalar.
2. **`lagfix` mejora (> `original` en las 4 sesiones) pero NO PASA** ⇒ el bug explica parte del
   "peor que el azar" pero la idea no tiene edge. Si queda ≥ mediana del control: "≈ azar". El fix
   igual se propone porque es un error de cálculo, pero **no** se espera que vuelva rentable a
   AIdan ⇒ el camino es rediseñar desde una hipótesis, no emparchar.
3. **`lagfix` ≤ `original`** en 3+ sesiones ⇒ el desfase no era la causa. Se documenta y se sigue
   con los problemas de diseño (tendencia sin neutral, niveles de ruido, confianza colineal, costo
   vs stop).

**No se afina nada sobre esta corrida**: ni umbrales ni índices distintos a los 4 de arriba. Si
aparecen otras variantes "que podrían andar mejor", van a otro criterio declarado.

## Límites (heredados de Fase 2)

Solo trigger `structure`; sin filtros del loop vivo; sin slippage ni spread variable;
`htf_bias=None`; un backtest infla ~20-30% vs real.
