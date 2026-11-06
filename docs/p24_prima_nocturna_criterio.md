# P24 — Prima nocturna en índices: criterio declarado ANTES de medir (5-nov-2026)

**Hipótesis (Cliff-Cooper-Gulen 2008; Lou-Polk-Skouras 2019):** en EE.UU. casi todo el retorno de las acciones
se gana entre el cierre y la apertura del contado; el tramo intradía rinde ~0. Tipo **A/B** de la escalera
(`docs/fuentes_de_ventaja_2026-11-04.md`): premio por cargar el riesgo de la noche, no adivina dirección intradía.

**El riesgo conocido:** el CFD cobra financiación justo por la noche que se mantiene.

## Datos
- `.cache_p1/M15` (MT5 ICMarkets, bajado 10-oct): US30, USTEC (principales), DE40 (descriptivo, otra sesión).
  Desde ~may-2020 hasta 2026-10-09. Hora del server = Nueva York + 7 h todo el año (verificado en P12).
- Costo, leído de MT5 el 5-nov-2026 con AIdan cerrado (`symbol_info`, solo lectura):

| Símbolo | swap largo por lote y noche | % del precio por noche | triple |
|---|---|---|---|
| US30 | −14,416 USD | ~0,027% | viernes |
| USTEC | −7,687 USD | ~0,027% | viernes |
| DE40 | −6,07 EUR | ~0,023% | viernes |

  Se aplica el swap ACTUAL a todo el período, como % del precio (swap / precio de hoy) × noches calendario entre
  entrada y salida. Es **cota alta** para 2020-22 (tasas ~0). Spread = el de la vela de entrada + el de la de salida.

## Regla (fija, sin parámetros que buscar)
- **EE.UU. (US30, USTEC):** largo en la apertura de la vela de 16:00 ET (23:00 server) → salida en la apertura de
  la vela de 09:30 ET (16:30 server) del siguiente día hábil con datos. Viernes → lunes (3 noches).
- **DE40:** largo a las 17:30 Berlín (cierre Xetra) → salida 09:00 Berlín del siguiente día hábil (convertido a
  hora del server con zonas horarias reales).
- Si falta alguna de las dos velas, la noche no se cuenta (se reporta cuántas faltan).
- Retorno neto por noche en % del precio.

## Control (placebo)
Mismo instrumento, misma cantidad de noches, pero con la entrada en una vela **al azar del mismo día** y la salida
con la **misma duración** que la noche real (mismos costos). 2000 repeticiones → percentil 95 de la media.
Responde: ¿esta ventana tiene algo especial, o es la deriva alcista 2020-26 que gana cualquier ventana larga?
(La lección de P9: el neto positivo en índices era la deriva.)

## Criterios (PASA = los 5)
1. n ≥ 250 noches en US30 y en USTEC.
2. Pool US30+USTEC: media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas del pool con media neta > 0.
4. Media neta real > percentil 95 del control, en US30 **y** en USTEC.
5. US30 y USTEC con media neta > 0 cada uno.

## Descriptivo (no decide)
- Bruto (sin swap ni spread) y neto con la mitad del swap (aprox. 2020-22).
- Tramo intradía (09:30 → 16:00 ET, solo spread): el paper dice que debería dar ~0.
- DE40 con su sesión.

## Si PASA
No se activa. Siguiente paso a proponer al user: papel en vivo + US500/STOXX50 nunca mirados como fuera de muestra.
## Si NO PASA
Cerrar prima nocturna en CFDs de índices con este costo. No buscar otra hora de entrada/salida.
