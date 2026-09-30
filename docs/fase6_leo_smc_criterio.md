# Fase 6 — Setup 1 de Leo (SMC) · criterio declarado ANTES de medir

**Fecha: 29 Sep 2026.** Commiteado antes de escribir el tool y de ver un solo número.
Fuente del método: `docs/leo_setup1_notas.md` + respuestas de Leo del 29-sep (21:03-21:13),
que **confirmó la traducción a reglas** ("te confirmo que es así como buscaría yo operaciones").

## Respuestas de Leo (textual resumido)
- **Dirección:** H4 da la dirección; si H1 coincide, mejor; si no, puede ser un retroceso.
- **Zona M15:** la decisional es donde toma impulso y rompe estructura; el movimiento se origina en el
  **extremo**, donde muchas veces el precio vuelve (antes: "yo elegiría operar en M15 en el extremo").
- **Antigüedad:** no por horas; vale mientras dure la estructura que se viene haciendo en H4.
- **Entrada:** así es (el precio entra a la zona, en M5 rompe con cuerpo el último mínimo = CHoCH,
  entrada a mercado en ese cierre).
- **Stop:** arriba del máximo de la zona, **unos 10 pips máximo** (es temporalidad baja).
- **TP:** **uno solo**, levemente por debajo del mínimo de la estructura ("operamos scalping").
  Si el precio se va hacia la zona del TP, **mover el SL a la entrada**.
- **Anulación por tiempo:** si pasa mucho tiempo se cancela, pero en temporalidad baja casi no pasa.
- **Noticias:** no operar de **5 min antes a 5 min después** de una noticia.

## Reglas mecánicas (congeladas; descrito para bajista, alcista es el espejo)
Velas M15, H1 y H4 armadas desde el M5 del cache `.cache_fase2/M5_500000`.

1. **Swings:** fractal de 2 velas a cada lado (máximo/mínimo local de 5 velas), confirmado 2 velas
   después (sin mirar el futuro).
2. **Estructura por temporalidad (H4, H1, M15):** bajista cuando el último evento es un **cierre** por
   debajo del último mínimo de swing confirmado (BOS con cuerpo); alcista, un cierre por encima del
   último máximo. Una mecha no cambia la estructura.
3. **Dirección:** se opera solo si **H4 y H1 coinciden** (si no coinciden, es un retroceso ⇒ no hay trade).
4. **Zona (extremo de M15):** con M15 bajista, el **extremo** es el máximo de swing de M15 más alto
   desde que M15 pasó a bajista (el origen de la pierna). La zona es la última vela M15 alcista
   (cierre > apertura) a la altura de ese máximo o antes: de su **mínimo** hasta el **máximo de swing**.
   Una zona por pierna; se reemplaza si M15 hace una pierna nueva.
5. **Vigencia:** la zona muere si una vela M15 **cierra por encima** de su techo, o si cambia la
   dirección de H4 o de H1.
6. **Entrada:** el precio (M5) entra a la zona. Desde ahí se toman los mínimos de swing de M5 que se
   formen; **CHoCH = cierre M5 por debajo del último mínimo de swing de M5** formado después de entrar
   a la zona. Entrada a mercado en el cierre de esa vela. Un trade por zona.
7. **Stop:** `max(techo de la zona, máximo alcanzado desde que entró a la zona) + 0,5 pip`. Si la
   distancia al stop es **mayor a 10 pips, no se opera**.
8. **TP único:** el mínimo de la pierna de M15 (el más bajo desde el extremo) **− 0,5 pip**. Si el TP
   queda a menos de 1 pip de la entrada, no se opera.
9. **Break-even:** cuando el precio recorre el **50% del camino al TP**, el stop pasa a la entrada
   (desde la vela siguiente).
10. **Salida por tiempo:** lo que siga abierto se cierra al fin del día del server.
11. Vela con stop y TP a la vez ⇒ cuenta el stop (conservador).

## Enmienda 1 (29-sep, ANTES de correr ningún número)
La regla 4 decía "el máximo de swing de M15 más alto **desde que M15 pasó a bajista**". Eso excluye el
techo del movimiento previo y termina marcando el último máximo antes de la ruptura, que es la zona
**decisional** de Leo, no su extremo ("el origen del movimiento general"; en su captura el extremo está
junto al máximo de H1). Se detectó con un test sintético de la función de estructura, no mirando
resultados. **Regla corregida:** extremo = el swing high **más alto confirmado desde el último BOS alcista**
de M15 (el techo del movimiento previo), reemplazado por uno más alto si aparece mientras siga bajista.
La decisional queda como estaba: el swing high vigente en cada BOS bajista. Espejo para alcista.

## Costos
Comisión round-turn + spread de la vela de entrada (mínimo de la barra ⇒ cota optimista). Sin swap
(sale en el día). **Sin filtro de noticias:** el cache no tiene el calendario histórico. Es un límite
declarado (las ventanas de ±5 min son ~3% del día) y **no se aproxima a posteriori**.

## Control
Por par: mismas cantidad de trades y proporción compra/venta, entradas en velas M5 al azar, con
**distancias de stop y de TP tomadas de los trades reales** (sorteadas), mismo break-even, misma salida
a fin de día, mismos costos. 200 repeticiones.

## Criterio para PASAR — las 5, sobre los 20 pares de Fase 1
1. media neta por trade > 0
2. límite inferior del CI95 bootstrap > 0
3. media neta > 0 en las dos mitades (corte por fecha)
4. media neta > **percentil 95** del control (un solo candidato)
5. media neta > 0 en al menos el **60% de los pares** en que opera

**Si pasa** ⇒ los 6 pares reservados (CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD): media neta > 0
y > p95 del control. Solo con las dos ⇒ shadow en vivo. **Si no pasa** ⇒ cerrado para esta data; no
se prueban otras definiciones de zona, de swing ni de stop.

**Secundarios descriptivos (NO deciden):** la zona **decisional** en lugar del extremo; y la entrada
agresiva (orden límite en el borde de la zona, sin esperar el CHoCH), que Leo marcó como riesgosa.

## Límites
Es MI traducción de un método discrecional, aunque Leo la confirmó: el ojo de Leo puede capturar cosas
que estas reglas no. Sin noticias, sin slippage, spread optimista, 5 de los 20 pares con 1,6 años.
