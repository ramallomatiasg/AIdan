# P13 — A1 (reversión a 2σ) como OPCIÓN BINARIA — criterio declarado ANTES de mirar los reservados

**Fecha:** 23-oct-2026. **Tool:** `tools/backtest_p13_a1_binaria.py` (read-only, sin MT5, no toca la DB).
Lee `.cache_fase2/M5_500000`.

## De dónde sale

El user preguntó si otro broker (p. ej. IQ Option, opciones binarias) cambiaría el resultado. En una binaria lo
único que importa es **acertar la dirección a la expiración**; el tamaño del movimiento no cuenta. Empatar con
payout `p` exige acertar `1/(1+p)`: 55,6% con payout 80%, 54,1% con 85%, 52,6% con 90%.

Medición exploratoria del 23-oct (scratch, EN MUESTRA: A1 se eligió en Fase 3 sobre estos 20 pares, aunque a H96,
no a 15 min), una posición por par a la vez, empates excluidos:
A1 a 15 min, 20 pares: **54,3%** (n=522.531, CI [54,2; 54,5]); solo EURUSD 53,5% (n=32.215). A 30 min 54,1%,
1 h 53,8%, 8 h 51,4%. P4 (lead-lag) en cambio ~50-51%.
⇒ A1 acierta seguido pero por poco movimiento: en spot el costo en pips se lo come; en binaria el pago no
depende del tamaño. **Es la primera vez que una señal de esta línea quedaría del lado bueno de un costo.** Como es
en muestra, decide la prueba fuera de muestra.

## Prueba (congelada)

- Señal `gen_A1` (importada), M5, entrada al close de la vela señal, una posición por par a la vez.
- Gana si `close[i+H]` está a favor de la dirección; pierde si en contra; empate (igual) se excluye (en IQ Option
  el empate devuelve el monto).
- **Principal: H3 (15 min).** Secundarios H1 (5 min), H6, H12.
- **Universo: SOLO los 6 reservados** (CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD), nunca mirados para A1.
  Una sola corrida; el tool se niega a repetirla.

## Criterio de PASA (H3, pool de los 6)

1. n ≥ 20.000.
2. Límite inferior del CI95 de Wilson del acierto **> 52,6%** (empata con payout 90%).
3. Acierto > 52,6% en las dos mitades cronológicas.
4. ≥ 4 de 6 pares con acierto > 52,6%.

**PASA FUERTE** si además el límite inferior del CI > 54,1% (empata con payout 85%).

**Si pasa:** la línea siguiente es medir el payout REAL y el precio de la plataforma (el feed de un broker de
binarias es suyo, no el de ICMarkets) en una cuenta demo, en shadow, antes de cualquier automatización.
**Si no pasa:** cerrada la idea de binarias con A1; no se barren horizontes ni umbrales.

## Límites declarados

- El precio de entrada es el close de la vela M5 de ICMarkets; en una plataforma de binarias se entra segundos
  después y a la cotización de esa plataforma ⇒ el acierto real puede ser menor.
- Las expiraciones de las plataformas a veces son a hora fija del reloj y no exactamente +15 min.
- El payout varía por activo y por hora; fuera de horario baja.
- Las binarias son productos de un formador de mercado, prohibidos para minoristas en la UE, el Reino Unido y
  Australia. Esto es una medición, no una recomendación de operar con plata real.
