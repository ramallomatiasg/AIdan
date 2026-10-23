# P13b — SHADOW en vivo de A1 como opción binaria (precio y payout de la plataforma) — criterio declarado ANTES de juntar

**Fecha:** 23-oct-2026. Pedido del user: *"armá un shadow en una cuenta demo de binarias para medir el payout y
el acierto reales de A1 en horario líquido"*.

## Por qué

P13 (backtest) pasó su criterio, pero el diagnóstico mostró que el acierto alto venía del bid de MT5 en el rollover
y en velas de spread ancho. En horario líquido con spread normal quedó en **52,1-52,6%**, justo el empate con
payout 90%. Las dos cosas que el backtest NO puede medir son: **(a)** el acierto sobre el precio de la PLATAFORMA
de binarias (que cotiza su propio precio, sin el artefacto del bid de ICMarkets) y **(b)** el payout REAL que
paga. Esto las mide en vivo, sin operar.

## Plataforma

**Deriv** (API oficial por WebSocket, cuenta demo gratis). IQ Option no tiene API oficial: automatizarla requiere
librerías no oficiales contra sus términos ⇒ descartada. Verificado el 23-oct: las velas de forex de Deriv se leen
sin cuenta; las COTIZACIONES de contratos (payout) exigen un `app_id` propio registrado en developers.deriv.com
(el `app_id` público de prueba, 1089, devuelve "This trade is temporarily unavailable"). Por eso el shadow corre
en dos niveles:
- **Sin `DERIV_APP_ID`:** mide el acierto sobre el precio de Deriv (lo que se puede medir hoy).
- **Con `DERIV_APP_ID`** (lo carga el user en `.env` después de registrar la app): además pide la cotización de
  cada contrato y guarda el payout real. **Nunca compra**: el módulo no tiene la llamada `buy` (test sobre el fuente).

## Qué hace (congelado)

- Tool `tools/shadow_binaria.py`, proceso propio (no corre dentro de AIdan.exe ⇒ sin rebuild), base propia
  `%APPDATA%/AIdan/state/binary_shadow.db`. No toca `financial_news.db` ni MT5.
- **Horario líquido:** lunes a viernes, **07:00-16:00 UTC** (= 10-19 server en horario de verano de NY, la ventana
  del diagnóstico de P13; se mantiene fija en UTC todo el año).
- **Instrumentos:** frxEURUSD, frxGBPUSD, frxUSDJPY, frxAUDUSD, frxUSDCHF, frxUSDCAD, frxEURGBP, frxEURJPY,
  frxGBPJPY, frxAUDJPY (los que la API devuelva; los que no, se loguean y se saltean).
- **Señal A1, idéntica a `gen_A1`:** en cada cierre de vela M5 de Deriv, z = (close − MA20) / desvío poblacional
  20 del close; z > +2 ⇒ PUT, z < −2 ⇒ CALL. Una señal abierta por instrumento a la vez.
- **Entrada:** el último tick de Deriv al momento de la señal. **Expiración:** 15 min después. **Salida:** el último
  tick ≤ expiración. Gana si el precio de salida está a favor; empate se registra aparte (no puntúa).
- Con `DERIV_APP_ID`: en el momento de la señal, cotización `proposal` (stake $10, Rise/Fall 15 min) ⇒ se guarda
  `payout`, `ask_price` y el `spot` de la cotización.

## Criterio (scorer `tools/score_shadow_binaria.py`, NO mover)

- **Lectura:** con n ≥ 400 señales resueltas (sin empates).
- **PASA** si las dos:
  1. Límite inferior del CI95 de Wilson del acierto > **break-even del payout real mediano**
     (break-even = stake/payout). Sin payout medido, se reporta contra 52,6% (payout 90%) y el veredicto queda
     **PROVISORIO**.
  2. EV por $1 con el payout real de cada señal > 0, con CI95 bootstrap cuyo límite inferior > 0 (solo con payout).
- **Apagar** si a n ≥ 800 no pasa: borrar la tarea programada.
- **Si pasa:** el próximo paso es comprar de verdad en la cuenta DEMO de Deriv (contratos reales en papel, con su
  entrada y salida oficiales) — decisión del user, con otro criterio declarado antes.

## Límites

- La entrada real de Deriv es el tick SIGUIENTE a la compra; acá es el último tick al pedir la señal (segundos de
  diferencia).
- El payout de Deriv puede no ser el de IQ Option ni el de otra plataforma.
- Ritmo esperado (del backtest): ~6 señales por instrumento por día en el horario ⇒ n=400 en ~1-2 semanas.
