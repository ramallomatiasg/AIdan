# Fase 4 — planes PLANIFICADOS (estilo Leo + evidencia publicada) · criterio declarado ANTES de medir

**Fecha: 23 Sep 2026.** Commiteado antes de escribir el tool y de ver un solo número. Si la lista, los
parámetros o el criterio se cambian después de ver resultados, el hallazgo no vale.

## Por qué

Fases 2/2b/3/3b refutaron la forma REACTIVA (detectar y entrar a mercado en M5/M15): la ruptura es peor
que el azar y la mejor reversión le gana al azar pero no al costo. El user (23-sep) describe el método
de su amigo Leo: **planificar** con la estructura del día o del día siguiente, dejar la orden **esperando
en el nivel**, SL del otro lado, **TP escalonado en 3 partes**, pocas operaciones. Eso nunca se probó.
Además pidió soluciones propias con base en evidencia externa. Se prueban juntas, con control por
pruebas múltiples.

## Los 8 candidatos — CONGELADOS

Datos: cache `.cache_fase2/M5_500000`, **20 pares de Fase 1** (los 6 reservados NO se miran salvo que
un candidato pase). Día = día del server (00:00 server = 17:00 NY). UTC = server − 3 h con horario de
verano de EE.UU., − 2 h sin él. `ADR` = media del rango (high−low) de los 14 días previos.

### Salida común de los planes con nivel (L1, L2, L3, E1)
- `R` = distancia al SL. Posición en **3 partes iguales**: TP1 = 1R, TP2 = 2R, TP3 = 3R.
- Tocado TP1, el SL de las 2 partes restantes pasa a la entrada (break-even) desde la vela siguiente.
- Lo que siga abierto se cierra al cierre de la última vela del día del server.
- Si en una vela se tocan SL y un TP, cuenta el **SL** (conservador). En la vela del fill solo se
  evalúa el SL, nunca un TP.
- **Fill de la orden límite**: venta en L si `high ≥ L`; compra en L si `low ≤ L`. Si la vela abre del
  otro lado del nivel, fill en el open. Una orden por nivel por día; se cancela al fin del día.

### Familia L — el método de Leo, en versiones estándar (manuales, NO optimizadas)
- **L1. Máximo/mínimo del día anterior (fade).** Cada día: venta límite en el máximo de ayer y compra
  límite en el mínimo de ayer. SL = 0,25 × ADR del otro lado del nivel.
- **L2. Bollinger H1 + vela T.** Velas H1 (armadas desde M5). Si una H1 toca la banda superior de
  Bollinger(20, 2) y es una vela T de agotamiento (mecha superior ≥ 60% del rango y cierre en el 40%
  inferior) ⇒ venta al open de la H1 siguiente; simétrico abajo. SL = extremo de la vela T + 0,1 × ATR14
  de H1.
- **L3. Retroceso a favor de la tendencia diaria, en el nivel planificado.** Tendencia D1 alcista =
  cierre de ayer > SMA20 diaria **y** SMA20 hoy > SMA20 de hace 5 días. En alcista, SOLO la compra
  límite en el mínimo de ayer; en bajista, SOLO la venta en el máximo de ayer. SL = 0,25 × ADR.

### Familia E — evidencia publicada (formulación propia, parámetros fijos del paper o manuales)
- **E1. Números redondos** (Osler 2003, *J. of Finance*: las órdenes de take-profit se agrupan en
  números redondos y el precio revierte ahí; los stops se agrupan justo detrás). Niveles cada 50 pips
  (xx00 / xx50; en JPY cada 0,50). Cada día: venta límite en el primer redondo por encima del open del
  día, compra límite en el primero por debajo. SL = 0,25 × ADR.
- **E2. Estacionalidad horaria** (Breedon & Ranaldo 2013, *JMCB*: las monedas se deprecian durante su
  horario local). Ventanas UTC: EUR/GBP/CHF 07-12 · USD/CAD 13-20 · JPY/AUD/NZD 00-06. Al inicio de la
  ventana de una moneda: si es la BASE del par (y la cotizada no está en horario) ⇒ venta; si es la
  COTIZADA ⇒ compra. Salida al fin de la ventana. Sin SL/TP.
- **E3a. Dólar ANTES del fixing de Londres** (Krohn, Mueller & Whelan 2024, *J. of Finance*: el USD se
  aprecia en la previa de los fixings y se deprecia después). Comprar USD desde 60 min antes del fixing
  de las 16:00 Londres hasta el fixing. Solo los 7 pares con USD.
- **E3b. Dólar DESPUÉS del fixing de Londres.** Vender USD desde el fixing hasta 60 min después.
- **E4. Momentum de series temporales** (Moskowitz, Ooi & Pedersen 2012; Menkhoff et al. 2012). Cada
  lunes al arranque del día: dirección = signo del retorno de los últimos 60 días (cierres diarios
  hasta el viernes). Mantener hasta el lunes siguiente.

*No se prueba ahora:* rebalanceo de fin de mes (Melvin & Prins 2015) — necesita retornos de índices
bursátiles, que el cache no tiene.

## Costos (en pips, por trade)
Comisión round-turn del par + **spread de la vela de entrada** (MT5 guarda el mínimo de la barra ⇒ cota
optimista) + **swap real** por rollover cruzado (miércoles ×3, sábado/domingo 0).

## Control
Por candidato y por par: mismas cantidad de trades y proporción compra/venta, entradas en velas al
azar a mercado, **misma mecánica de salida** (planes con nivel: mismo SL de 0,25 × ADR del día, mismas
3 partes, cierre a fin de día; temporales: misma duración en velas) y mismos costos. 200 repeticiones.

## Criterio para PASAR — las 5, sobre los 20 pares
1. media neta por trade > 0
2. límite inferior del CI95 bootstrap > 0
3. media neta > 0 en las dos mitades (corte por fecha)
4. media neta > **percentil 99** del control (99 y no 95: se prueban 8 candidatos a la vez)
5. media neta > 0 en al menos el **60% de los pares** en que opera

**Si uno pasa** ⇒ el mismo test en los 6 reservados: tiene que dar media neta > 0 y > p95 del control.
E3a/E3b no tienen pares con USD entre los reservados ⇒ para ellos no hay out-of-sample por pares: se
declara que irían directo a shadow en vivo, y solo si pasan las 5.
**Solo con las dos cosas** se propone construirlo en **shadow**. Nunca directo a operar.
**Si ninguno pasa** ⇒ se reportan los 8 con su número y no se re-corta la data buscando un subconjunto.

## Límites
Sin slippage; el spread es optimista; el fill de la orden límite asume que tocar el nivel alcanza; swap
con el snapshot del 18-ago; 5 de los 20 pares tienen solo 1,6 años. Un "pasa" es permiso para shadow.
