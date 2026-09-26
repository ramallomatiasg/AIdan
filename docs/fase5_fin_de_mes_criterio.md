# Fase 5 — rebalanceo de fin de mes (Melvin & Prins 2015) · criterio declarado ANTES de medir

**Fecha: 26 Sep 2026.** Commiteado antes de escribir el tool y de ver un solo número.

## Por qué

Después de Fases 2-4 (unas 20 ideas de patrón de precio, todas refutadas con costos reales) la única
idea con evidencia publicada que no es un patrón de precio y quedaba sin probar es el **canal de
cobertura de fin de mes**: los fondos que tienen acciones extranjeras cubren la moneda **una vez por
mes, en el fixing de las 16:00 de Londres del último día hábil**. Si las acciones de un país subieron en
el mes, tienen que vender más de esa moneda para mantener la cobertura ⇒ la moneda se debilita en la
hora previa al fixing. Es un flujo **predecible de antemano**, no un patrón.

Fuente: Melvin & Prins (2015), *Equity hedging and exchange rates at the London 4 p.m. fix*, J. of
Financial Markets. Del paper (versión ECB 2013, §5.1, ecuación 3): retorno de la moneda **de 15:00 a
16:00 hora de Londres del último día del mes**; predictor = retorno de la bolsa **desde el cierre del
último día del mes anterior hasta el cierre del anteúltimo día del mes**; efecto 2004-2012: un 10% de
suba relativa ⇒ 14 pb de depreciación en esa hora. *Advertencia previa: el paper cubre 2004-2012, fue
publicado, y en 2015 la metodología del fixing cambió (ventana de 5 minutos). Lo más probable es que el
efecto se haya achicado.*

## Qué se mide (congelado)

- **Pares y bolsas** (índices CFD de MT5, cierres diarios): EURUSD ↔ STOXX50 · GBPUSD ↔ UK100 ·
  USDJPY ↔ JP225 · AUDUSD ↔ AUS200 · referencia de EE.UU. = US500.
- **Señal** (versión bilateral contra el dólar): `dif = retorno_bolsa_extranjera − retorno_US500` en el
  mes (definición de arriba). `dif > 0` ⇒ **vender** la moneda extranjera contra el USD en la ventana;
  `dif < 0` ⇒ comprarla. (En USDJPY, vender JPY = comprar USDJPY.) `dif = 0` o falta de dato ⇒ sin trade.
- **Último día del mes** = último día hábil del mes calendario (fecha de Londres) con velas M5 de FX.
- **Ventana**: de 15:00 a 16:00 hora de Londres (UTC+1 con horario de verano británico, UTC sin él).
  Entrada al open de la vela de las 15:00, salida al cierre de la última vela antes de las 16:00. Solo
  ventanas completas (12 velas M5).
- **Datos FX**: cache `.cache_fase2/M5_500000` (EURUSD, GBPUSD, USDJPY, AUDUSD: 6,7 años ⇒ ~80
  meses × 4 pares ≈ 320 trades).
- **Costos**: comisión round-turn del par + spread de la vela de entrada (mínimo de la barra ⇒ cota
  optimista). Sin swap (no cruza rollover).
- **Secundario descriptivo (NO decide)**: lo mismo con la ventana de 08:00 a 16:00 de Londres, y la
  correlación entre `dif` y el retorno de la ventana.

## Criterio para PASAR — las 5
1. media neta por trade > 0
2. límite inferior del CI95 bootstrap > 0
3. media neta > 0 en las dos mitades (corte por fecha)
4. media neta > **percentil 95** del control (un solo candidato ⇒ p95): 200 repeticiones con
   **días al azar que NO son fin de mes**, misma ventana de 15:00 a 16:00 de Londres, misma cantidad de
   trades y proporción compra/venta por par, mismos costos
5. media neta > 0 en al menos **3 de los 4 pares**

**Si pasa** ⇒ out-of-sample en monedas que no se miraron: **USDCAD ↔ CA60** y **USDCHF ↔ SWI20**, con la
misma regla (media neta > 0 y > p95 del control). Solo con las dos cosas ⇒ shadow en vivo (1 señal por
mes y par: la muestra forward es lenta y eso se acepta).
**Si no pasa** ⇒ cerrado; no se prueban otras ventanas, otros índices ni un umbral de `dif`.

## Límites
Índices CFD de un broker, no los índices de país del paper (MSCI); versión bilateral, no el panel
demeaned; el fixing real es a las 16:00 exactas y desde 2015 se calcula en 5 minutos; spread optimista;
~320 trades es una muestra chica comparada con Fases 2-4.
