# P33 — Pre-feriado en índices de EE.UU.: criterio declarado ANTES de medir (11-nov-2026)

**Hipótesis (Ariel 1990; Kim & Park 1994):** el día hábil anterior a un feriado de la bolsa de EE.UU. las
acciones rinden varias veces más que un día cualquiera. Tipo **B** de la escalera
(`docs/fuentes_de_ventaja_2026-11-04.md`): efecto de calendario, no mira el gráfico. Dura 1 día ⇒ paga una sola
noche de swap (lo que mató a P24 y le restó a P25). Prior bajo-medio: publicado hace décadas.

## Datos
- `.cache_p1/M15` (MT5 ICMarkets): **US30, USTEC**, may-2020 → 2026-10-09. Hora del server = Nueva York + 7 h.
- Antes de declarar solo se miró **qué velas existen** alrededor de cada feriado (no precios ni retornos).
- Costo: el de P24/P25 — swap ACTUAL de MT5 (5-nov) × noches calendario + spread de la vela de entrada y de salida.

## Feriados (por regla, no por lista a mano)
NYSE: Año Nuevo, Martin Luther King (3er lunes de enero), Presidentes (3er lunes de febrero), Viernes Santo,
Memorial Day (último lunes de mayo), Juneteenth (desde 2022), 4 de julio, Labor Day (1er lunes de septiembre),
Acción de Gracias (4to jueves de noviembre), Navidad. Sábado ⇒ se observa el viernes (salvo Año Nuevo, que no se
observa); domingo ⇒ el lunes. Cierres no programados (duelo del 9-ene-2025) no cuentan.

## Regla (fija, sin parámetros que buscar)
- **Día pre-feriado** = último día de semana, no feriado, antes del feriado.
- **Entrada:** apertura de la vela de las 16:00 ET (cierre del contado) del día hábil anterior al pre-feriado.
- **Salida:** apertura de la vela de las 16:00 ET del día pre-feriado. Si esa vela no existe (cierre temprano de
  las 13:00: 3 de julio, 24 de diciembre), apertura de la vela de las 12:45 ET.
- Evento sin vela de entrada o de salida ⇒ se descarta y se cuenta.
- Retorno neto por evento en % del precio. Un evento por feriado y por instrumento.

## Control (placebo)
Mismo instrumento, mismo año, **mismo día de la semana** que el pre-feriado: cierre 16:00 del día hábil anterior
→ cierre 16:00 de un día al azar que no sea pre-feriado ni feriado, mismos costos. 2000 repeticiones de la media
de n eventos → percentil 95. Responde: ¿el día es especial o es la deriva alcista 2020-26?

## Criterios (PASA = los 5)
1. n ≥ 50 eventos en US30 y en USTEC.
2. Serie **por evento** (promedio de US30 y USTEC en cada feriado, una observación por feriado — lección de P25:
   no contar dos índices que se mueven juntos como independientes): media neta > 0 y extremo inferior del CI95
   bootstrap > 0.
3. Las dos mitades cronológicas de esa serie con media neta > 0.
4. Media neta real > percentil 95 del control, en US30 **y** en USTEC.
5. US30 y USTEC con media neta > 0 cada uno.

## Descriptivo (no decide)
Bruto, % de eventos ganadores, media del control, y el resultado sin los eventos de cierre temprano.

## Si PASA
No se activa. Proponer al user: papel en vivo + índices nunca mirados (US500) como fuera de muestra.
## Si NO PASA
Cerrar pre-feriado en CFDs de índices. No buscar otra ventana (2 días antes, día posterior) ni un subconjunto
de feriados.
