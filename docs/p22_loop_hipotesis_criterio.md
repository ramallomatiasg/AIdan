# P22 — loop de hipótesis: la IA propone, el arnés prueba, aprende de TODO lo probado — criterio declarado ANTES de medir

**Fecha:** 28-oct-2026. **Pedido del user:** que AIdan sea una IA que analiza el mercado con varios factores, aprende de
los errores y se pule sola (*"si fuese inteligente sabría pulirse"*), y que **no gire sobre una misma hipótesis:
que aprenda de todo**. **Tools:** `tools/hyp_data.py` (datos públicos + catálogo de features) y `tools/hyp_loop.py`
(registro, evaluador, proponente IA). Read-only respecto de AIdan: sin MT5, no toca la DB de AIdan, no manda órdenes;
escribe solo en su base `%APPDATA%/AIdan/state/hypothesis_loop.db` y en el cache `.cache_p22/`.

## Por qué así (y no "que el bot aprenda de sus trades")

AIdan hace ~7 trades/día: una lección sacada de 1 trade es una anécdota, y el resumen post-trade del LLM marcó
"buena entrada" en el 93% de los perdedores. Este loop aprende de **25 años de datos públicos**, y mira **más que
precio** (lo único que miró AIdan hasta ahora y que salió peor que el azar intradía).

## Datos (públicos, gratis, sin cuenta)

- **Precio:** 7 monedas contra USD, diario (FRED H.10, tasa de mediodía de NY): EUR, JPY, GBP, CHF, CAD, AUD, NZD, 1999 →.
- **Posicionamiento:** CFTC COT legacy, futuros, semanal: neto de especuladores (no comerciales) y de comerciales
  como % del interés abierto, por moneda.
- **Tasas:** interbancaria a 3 meses por país (OECD vía FRED, mensual); bono de EE.UU. a 2 y 10 años (diario).
- **Otros mercados:** VIX, dólar amplio (DTWEXBGS, desde 2006), petróleo WTI.

**Sin mirar el futuro (reglas fijas):** el COT del martes T se usa desde el lunes T+6 (se publica el viernes); las
tasas mensuales del mes m se usan desde el primer día del mes m+2; las series diarias de cierre (bonos, VIX, dólar,
petróleo) del día d se usan desde d+1; el precio de mediodía del día d se usa el día d.

## Qué puede proponer la IA (lista cerrada)

Una hipótesis = **moneda** (una de las 7, o `ALL` = cartera de las 7) + **1 o 2 condiciones** (`feature > umbral` o
`feature < umbral`, Y lógico) + **posición** (`long_fx` / `short_fx` = comprar o vender la moneda contra el USD
mientras se cumplen) o **simétrica** (1 condición: arriba del umbral una posición, abajo de −umbral la contraria)
+ **horizonte** (5, 10 o 20 días hábiles) + **mecanismo** (quién paga y por qué; obligatorio). Features y umbrales
salen del catálogo de `hyp_data.py` (`CATALOG`); nada fuera de él se evalúa. La IA no escribe código.

## Cómo se mide cada hipótesis (fijo)

- Se mira la regla cada `h` días hábiles (períodos que no se pisan) y se mantiene la posición `h` días.
- **Costo** (cuenta IC Markets Raw, por ida y vuelta, en pips): EUR 0,8 · JPY 0,9 · GBP 1,0 · AUD 1,0 · CHF 1,2 ·
  CAD 1,2 · NZD 1,3; se cobra la mitad al entrar y la mitad al salir (dar vuelta = ida y vuelta completa).
- **Swap:** la posición cobra o paga el diferencial de tasas a 3 meses por día calendario, menos **1% anual** de
  margen del broker, siempre en contra.
- Resultado = retorno neto por período **con posición abierta**, en puntos básicos del nominal. `ALL` = promedio de
  las monedas con posición en ese período.

## Criterio (NO mover)

**Etapa A — descubrimiento (1999 → 2014).** Pasa si se cumplen las 5:
1. ≥ 30 períodos con posición.
2. Media neta > 0.
3. CI95 por bootstrap en bloques de 4 períodos (5.000 remuestreos): límite inferior > 0.
4. Media > 0 en las dos mitades cronológicas del descubrimiento.
5. Le gana al azar: media > p95 de 200 controles que corren la MISMA serie de posiciones en el tiempo (corrimiento
   circular aleatorio por moneda: misma exposición, misma persistencia, sin la información).

**Etapa B — reserva (2015 → último dato).** Solo si pasó A. La IA nunca ve resultados de la reserva. Pasa si media > 0
y p unilateral por bootstrap < **0,05 / k**, donde k = cantidad de hipótesis que llegaron alguna vez a la reserva
(incluida esta): cada mirada a la reserva se paga.

**Etapa C — shadow hacia adelante.** Si pasó B queda en `shadow` con fecha de promoción; cada vuelta se mide SOLO
sobre períodos posteriores a esa fecha. Con ≥ 26 períodos con posición: media neta > 0 ⇒ `candidata` (se le lleva al
user con Plan / Razón / Pros / Contras para operarla en demo); ≤ 0 ⇒ `falló_shadow`. **Nada pasa a producción solo.**

**Control positivo en cada vuelta (si falla, la vuelta se anula):** una señal sintética que acierta la dirección
del período siguiente el 60% de las veces TIENE que pasar A en EUR; 20 señales al azar NO pueden pasar A más de 3
veces. Así se sabe que el arnés detecta información cuando la hay y no inventa cuando no la hay.

## "Aprender de todo" — reglas contra girar sobre la misma idea

- **La memoria es todo el registro**, lo que pasó y lo que no. Antes de proponer, la IA recibe (calculado por código,
  no opinado): por feature, cuántas veces se probó, cuántas pasaron A y el mejor/peor resultado; por familia, si está
  cerrada; qué features nunca se probaron; y las familias ya refutadas por el proyecto antes de este loop.
- **Familia** = las features usadas, el sentido de cada condición y la posición. Cambiar umbral, horizonte o moneda
  **no es una idea nueva**: es una variante de la misma familia.
- **Familia cerrada** después de 3 variantes que no pasan A: el validador rechaza propuestas nuevas en ella.
- **Duplicados** (misma familia + moneda + horizonte + umbrales) se rechazan.
- **Máximo 1 hipótesis por familia por vuelta**, y si sobran propuestas se priorizan las que usan features menos
  probadas (exploración antes que refinamiento).
- Todo lo rechazado también queda registrado con el motivo.

## Límites (declarados)

- Precio de mediodía de NY, no un precio operable exacto: sirve para horizontes de días, no intradía.
- Con muchas hipótesis, en A pasan algunas por azar (~5%): por eso existen B (con su corrección) y C.
- El COT de NZD empieza ~2004, el dólar amplio 2006 y algunas tasas OECD dejan de publicarse: dato faltante = sin
  señal (la hipótesis queda plana ese período).
- Nada de esto mide si AIdan intradía puede mejorar: mide si existe información en datos que AIdan no mira.

**Enmienda 1 (28-oct, después de 5 vueltas, por pedido del user de que no gire sobre la misma idea — NO toca el gate
de pase):** (a) una familia cuya mejor variante dio neto ≤ 0 se cierra a las 2 variantes (no a las 3); (b) cuando ya
se probaron todas las features, no se aceptan variantes de familias de una sola fuente ya probadas: solo
combinaciones o familias nuevas; (c) si la IA propone menos de la mitad válida, se le devuelven los rechazos y
propone una vez más en la misma vuelta.
