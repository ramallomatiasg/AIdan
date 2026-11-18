# P54 — Comprar la stablecoin cuando pierde la paridad: criterio declarado ANTES de medir (18-nov-2026)

**Hipótesis:** cuando una stablecoin respaldada cae debajo de 1 contra USDT, la venta es de pánico (o de quien
necesita salir ya) y la emisora la rescata 1:1 ⇒ comprarla barata y venderla al volver paga un premio por poner
liquidez cuando nadie quiere. Tipo **B** (liquidez/flujo). La cola es el depeg que no vuelve (UST, TUSD).

## Datos (verificado antes de declarar: solo que los pares existan y desde cuándo, **ningún precio**)
Velas de 1 h del spot de Binance (`api/v3/klines`, público), cache `.cache_p54/`. Universo FIJO de stablecoins en
dólares con par contra USDT: USDCUSDT (dic-2018), BUSDUSDT (sep-2019), TUSDUSDT (may-2018), PAXUSDT (oct-2018) →
USDPUSDT (sep-2021, misma moneda renombrada: PAX hasta que arranca USDP), FDUSDUSDT (jul-2023), DAIUSDT (jul-2020),
USDEUSDT (sep-2025), USD1USDT (may-2025), USDSUSDT (abr-2026). Solo se usan velas con volumen > 0.

## Regla (fija)
- **Señal:** cierre de una vela de 1 h < **0,995**. **Entrada (compra):** open de la vela siguiente.
- **Salida:** open de la vela siguiente al primer cierre ≥ **0,999**, o a las **168 h** (7 días) de la entrada, o la
  última vela con volumen si el par deja de operar (cuenta como lo que valga ahí: es la cola).
- Sin solapar: una nueva entrada en el mismo par necesita una señal posterior a la salida.
- Resultado = P_salida / P_entrada − 1 − costo (en USDT).
- **Costo:** comisión 0,10% × 2 + deslizamiento 0,10% × 2 = **0,40%** ida y vuelta. Pesimista: **0,80%**.
- **Episodio:** operaciones del mismo par que arrancan a menos de 30 días de la anterior = un episodio (comparten la
  causa) ⇒ el CI se agrupa por episodio.

## Control (placebo)
Mismo par, compras en horas al azar con cierre entre 0,999 y 1,001 (paridad normal) y la MISMA duración de cada
operación real; 2000 repeticiones de la media ⇒ percentil 95.

## Muestra
- **Descubrimiento:** entradas hasta 2024-12-31. **Reserva:** 2025 → nov-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 6)
1. n ≥ 8 operaciones en ≥ 4 episodios distintos.
2. Media neta > 0 y extremo inferior del CI95 > 0 (bootstrap agrupado por episodio, 5000).
3. Ganadas ≥ 75%.
4. Media neta > percentil 95 del control.
5. Media neta > 0 con el costo pesimista.
6. **Peor operación > −3%** (el riesgo que importa con capital chico: un depeg que no vuelve).

**Reserva:** media neta > 0 y peor operación > −3% (n esperado muy chico: solo confirma que no rompe).

## Descriptivo (no decide)
Por par y por episodio, mínimo tocado durante la operación (caída máxima intra-operación), horas en posición, cuánto
capital rinde por año si se tuviera $1.000 esperando (ganancia total / años de muestra).

## Límites
- Todo medido contra USDT: si el que se despega es USDT (hacia arriba), la señal también se activa.
- Velas de 1 h: el piso intrahora no se compra (conservador) y el deslizamiento real en pánico puede ser mayor.
- Pocos episodios ⇒ el resultado es más un "¿rompe o no?" que una estimación fina del premio.

## Si PASA
No se activa. Reserva; después papel en vivo con alerta (es raro: meses sin operar).
## Si NO PASA
Cerrar la compra de stablecoins en depeg. No probar otros umbrales (0,99 / 0,98), otros pares ni otros exchanges.
