# P21 — ¿un broker más barato salva alguna estrategia ya medida? — criterio declarado ANTES de medir

**Fecha:** 28-oct-2026. **Pedido del user:** *"si el problema es el broker que sale caro se averigua otro"*.
**Tool:** `tools/backtest_p21_broker.py` (read-only, sin MT5: usa los caches de velas de Fase 2; importa los arneses
originales, no los copia).

## Costos verificados (28-oct, páginas oficiales + comparadores)

- **IC Markets Raw (la cuenta actual):** USD 3,50 por lado por lote ⇒ **USD 7 ida y vuelta** (~0,70 pips en EUR/USD).
- **Fusion Markets Zero (el más barato):** USD 2,25 por lado ⇒ **USD 4,50 ida y vuelta** (~0,45 pips), spread desde 0,0.
  Comisión en FX y metales; índices sin comisión (igual que IC).
- **Interactive Brokers (IDEALPRO):** 0,2 pb por lado (~0,44 pips ida y vuelta) pero **mínimo USD 25.000 por orden y
  USD 2 por orden** ⇒ no sirve para una cuenta de ~USD 500 con lote 0,01. Descartado por tamaño, no por precio.

## Método

1. **Escritorio:** para cada estrategia con algo de información (bruto > 0 o le ganó al azar), bruto − costo con
   Fusion (comisión × 4,5/7, mismo spread y swap) − swap. Las que siguen ≤ 0 quedan cerradas: el broker no las salva.
2. **Re-medición:** las que dan > 0 en el escritorio se corren otra vez por su arnés ORIGINAL con la comisión de
   Fusion, y valen **las mismas condiciones de su criterio original** (A1 Fase 3b: las 5 a H96 sobre los 20 pares).

## Límites

- El spread del cache de MT5 es el MÍNIMO de cada barra (optimista) y se deja igual; el de Fusion puede ser distinto.
- El swap se deja el de IC (Fusion publica swaps parecidos, no verificado par por par).
- Cambiar de broker no cambia la señal: si una estrategia pierde ANTES de costos, ningún broker la salva.
