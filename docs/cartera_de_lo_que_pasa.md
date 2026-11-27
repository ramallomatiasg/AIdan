# Cartera de lo que pasa — AIdan

Pedido del user (20-nov-2026): *"quiero seguir probando ideas hasta encontrar todo lo que pasa y darle esfuerzo a todas
las que pasen juntas"*. Acá va TODO lo que pasó el descubrimiento y el fuera de muestra (reserva u otros instrumentos).
La rutina diaria lo actualiza cuando entra algo nuevo y mide la cartera combinada (read-only). Nada se activa sin el OK
del user.

| # | Qué es | Pasó | 2025-26 (lo reciente) | Papel en vivo | Riesgo principal |
|---|---|---|---|---|---|
| P15 | Carry de funding Binance (spot largo + perpetuo corto, BTC/ETH/SOL…) | desc. + reservados (+4,8 / +5,8%/año s/ capital) | ≈ 0, debajo de la letra | P19 (lectura ~25-ene-2027) | exchange; funding negativo largo |
| P21-A | Mismo carry en Hyperliquid | desc. + fuera de muestra (+6,2%/año) | debajo de la letra | P19 libro HL (lectura ~2-feb-2027) | exchange/contrato HL |
| P45 | Carry de funding HL en ~15 monedas | desc. (+7,3%/año, 14/15 > 0) | +2,7-2,8%, debajo de la letra | no | igual que P21-A, más monedas chicas |
| P39 | Vender volatilidad de BTC/ETH (Deribit) | BTC + ETH fuera de muestra | **negativo**; reserva con CI que cruza cero | P39b (diagnóstico ~13-dic) | colas (caída brusca) |
| P76 | Mismo carry en Deribit (BTC/ETH, reglas congeladas) | criterio (+3,75%/año vs letra 2,87%), sin reserva | +0,6% / +0,3%, debajo de la letra | no (mismo premio que P19) | exchange; 2022-26 +1,7%/año vs letra 4,0% |
| P57 | Vault HLP de Hyperliquid | desc. + reserva (+9,5% s/ letra, CI cruza cero) | +14% en 2025, +11% en 2026, bajando | no (propuesto, falta OK) | hackeo/manipulación (JELLY), puente |
| P80 | Prestar USD en el funding de Bitfinex (auto-renovación) | desc. (+10,0% s/ letra 2016-21) + reserva (+1,0% s/ letra, CI [+0,4, +1,5]) | 2025 +0,9%, 2026 +0,4% sobre la letra; 2024 −0,8% | no | exchange (hackeo 2016: −36%, devuelto en 8 meses); pesimista de la reserva −1%/año |

**Lectura honesta (20-nov):** todo lo que pasó es *premio por riesgo* en cripto, y casi todo rindió mucho en 2021-24 y
poco en 2025-26. Juntarlo reduce el riesgo de un solo exchange o de un solo mecanismo, pero muchas comparten el mismo
motor (el apalancamiento de los minoristas de cripto) ⇒ hay que medir la correlación, no suponer que diversifica.

**25-nov (P74):** la misma regla de P15 con datos de Bybit (jul-2021 → nov-2026) da +2,66%/año, igual que Binance en la
misma ventana (+2,65%), contra una letra media de 3,65% ⇒ el carry replica en otro exchange (bien) pero **desde 2021 no
le gana a la letra en ninguno de los dos** (2025 +0,9%, 2026 0%). Correlación diaria Bybit-Binance +0,57: sumar Bybit
reparte el riesgo de exchange, no agrega rendimiento.

**26-nov (P76 + primera medición de la cartera, `tools/cartera_combinada.py`, jun-2023 → oct-2026, letra 4,56%):**
Deribit pasa el criterio solo porque su historia incluye 2019-21 (2022-26: +1,7%/año vs letra 4,0%). En el período
común: carry Binance +2,7 · Bybit +2,7 · Deribit +2,5 · Hyperliquid +7,3%/año; **correlación mensual entre los carry
0,86-0,96** (un solo premio, cuatro contrapartes). HLP +47,7%/año (inflado en 2023-24 por depósitos, ver P57),
correlación con el carry 0,35-0,54. Cartera de los 5 a peso igual: +11,8%/año, caída máx 0,3%, peor mes −0,14% (−$1 con
$1.000); 2025 +4,8%, 2026 +1,9% ⇒ en lo reciente casi todo viene del HLP. Lo que diversifica de verdad es sumar otro
MOTOR, no otro exchange del mismo carry.

**26-nov, 2da corrida (P80 entra):** prestar USD en Bitfinex rinde +4,7%/año en el período común (letra 4,56%) ⇒ casi
nada sobre la letra, pero **es el libro menos correlacionado** (0,14-0,25 con el carry, 0,23 con HLP), sin meses
negativos y vol 0,35%. Cartera de los 6: +10,6%/año, caída máx 0,07%, peor mes −0,07%; 2025 +4,9%, 2026 +2,1%. Mismo
patrón que el resto: rendía mucho hasta 2021-23 y hoy apenas supera la tasa libre.

## Pendiente
- Sumar P45 (HL otras monedas) y P39 (libro diario de P39b cuando haya historia) a `tools/cartera_combinada.py`.
