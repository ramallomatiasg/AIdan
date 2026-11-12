# P35 — Demanda de cobertura al cierre de EE.UU.: criterio declarado ANTES de medir (11-nov-2026)

**Hipótesis (Baltussen, Da, Lammers & Martens 2021, *JFE*, "Hedging demand and market intraday momentum"):**
los dealers cortos de gamma y los ETF apalancados tienen que comprar al final de los días de suba y vender en
los de baja ⇒ el retorno del día hasta 30 min antes del cierre anticipa el de los últimos 30 min. Tipo **B**
de la escalera (flujo forzado a hora fija). Queda en el borde de lo cerrado (E, intradía): se acepta solo con
la regla del paper, sin parámetros propios. Si no pasa, no se buscan variantes.

## Datos
- `.cache_p1/M15` (MT5 ICMarkets): **US30, USTEC**, may-2020 → 2026-10-09. Hora del server = Nueva York + 7 h.
- Antes de declarar no se miró ningún retorno de estas ventanas.
- Costo: el de P24/P33 — spread de la vela de entrada + spread de la vela de salida (MT5 guarda el spread
  mínimo de la vela; contar los dos lo compensa). Sin swap (no cruza la noche). Comisión 0 (CFD de índice).

## Regla (fija)
- **Señal:** r = (apertura de la vela de las 15:30 ET − apertura de la vela de las 16:00 ET del día hábil
  anterior) / esta última. Días de la semana con las dos velas; se excluyen los días de cierre temprano
  (3 de julio, viernes después de Acción de Gracias, 24 de diciembre) y los feriados de la NYSE
  (calendario por regla de P33).
- **Descubrimiento / reserva:** primera mitad cronológica de los días válidos de cada índice = descubrimiento;
  segunda mitad = reserva. Umbrales = percentiles 20 y 80 de r en el descubrimiento de ese índice (congelados).
- **Operación:** r > p80 ⇒ largo; r < p20 ⇒ corto; si no, nada. Entrada en la apertura de la vela de las
  15:30 ET, salida en la apertura de la vela de las 16:00 ET. Una operación por día e índice.
- Retorno neto por operación en bps del precio.

## Control
Mismos días con señal, **signos permutados** entre ellos (mantiene la proporción largo/corto y la deriva del
tramo): 2000 repeticiones de la media → percentil 95. Responde: ¿la dirección del día importa o es el tramo?

## Criterios (PASA = los 5, todos sobre la RESERVA salvo el 3)
1. n ≥ 100 operaciones en la reserva en US30 y en USTEC.
2. Serie **por día** (promedio de los índices que operaron ese día, una observación por día): media neta > 0 y
   extremo inferior del CI95 bootstrap > 0.
3. El descubrimiento también con media neta por día > 0.
4. Media neta > percentil 95 del control, en US30 **y** en USTEC.
5. Largos y cortos con media neta > 0 cada uno (serie por día, reserva).

## Descriptivo (no decide)
Bruto, % ganadores, por año, pendiente de la regresión del último tramo contra r en todos los días.

## Si PASA
No se activa. Proponer: papel en vivo + US500 (nunca mirado) como fuera de muestra.
## Si NO PASA
Cerrar momentum intradía de cierre en CFDs de índices. No probar otro umbral, otro tramo (última hora,
15 min) ni el primer tramo del día.
