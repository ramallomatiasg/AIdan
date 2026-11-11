# P32 — Vencimiento trimestral (triple witching) en índices: criterio declarado ANTES de medir (10-nov-2026)

**Hipótesis (Stoll-Whaley 1987/1991; literatura de "options expiration week"):** en la semana del vencimiento
trimestral de opciones y futuros sobre índices (3er viernes de mar/jun/sep/dic) los dealers deshacen coberturas
en fecha fija y el índice tiende a subir; la semana siguiente revierte. Tipo **B** de la escalera
(`docs/fuentes_de_ventaja_2026-11-04.md`): flujo forzado de calendario, no mira el gráfico.

## Datos
- `.cache_p1/M15` (MT5 ICMarkets, bajado 10-oct): **US30, USTEC** (principales), **DE40** (descriptivo: Eurex
  vence el mismo 3er viernes), may/jun-2020 → 2026-10-09. Mismo reloj y mismas sesiones que P24/P25.
- Costo: el de P24/P25 — swap ACTUAL de MT5 (largo) × noches calendario + spread de la vela de entrada y de
  salida. Cota alta para 2020-22.

## Regla (fija, sin parámetros que buscar)
- Días hábiles = días de semana con vela de cierre del contado en el cache (igual que P25).
- Día de vencimiento = 3er viernes de mar/jun/sep/dic; si no es hábil, el hábil anterior.
- **Principal (semana del vencimiento):** largo desde el cierre del contado **5 días hábiles antes** del
  vencimiento hasta el cierre del contado **del día de vencimiento**.
- Un evento por trimestre y por instrumento. Retorno neto en % del precio.

## Control (placebo)
Mismo instrumento, mismo año, ventanas de 5 días hábiles que arrancan en un día hábil al azar que no se superponga
con la semana del vencimiento ni con la semana siguiente; mismos costos (noches reales). 2000 repeticiones de la
media de n eventos → percentil 95. Responde si la semana es especial o es la deriva alcista 2020-26.

## Criterios (PASA = los 5)
1. n ≥ 20 eventos en US30 y en USTEC (son ~25: **la potencia es baja y se declara**; con esto solo un efecto
   grande puede pasar).
2. Pool US30+USTEC: media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas del pool con media neta > 0.
4. Media neta > percentil 95 del control, en US30 **y** en USTEC.
5. US30 y USTEC con media neta > 0 cada uno.

## Descriptivo (no decide)
- Bruto, con mitad del swap, % ganadores.
- **Semana siguiente** (5 días hábiles después del vencimiento), retorno largo: la hipótesis dice negativo.
- DE40 con su sesión.

## Si PASA
No se activa. Paso siguiente a proponer al user: STOXX50/F40 (nunca mirados para esto) como fuera de muestra
y papel en vivo.
## Si NO PASA
Cerrar el vencimiento trimestral en CFDs de índices. No probar otra ventana, el vencimiento mensual ni la semana
siguiente como estrategia propia (sería buscar sobre la misma muestra).
