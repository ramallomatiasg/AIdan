# Research cuenta CENT — 19 Ago 2026 · VEREDICTO: DESCARTADA por costo

**Pregunta** (item 5 del roadmap de `RESEARCH_INVESTIGATION.md`): ¿una cuenta cent
(lote mínimo efectivo ÷100) destraba Kelly por track, meta-labeling, el track D1 y las
salidas parciales — los 4 cuellos cerrados como "depende del capital"?

**Gate pre-declarado ANTES de mirar precios**: si el costo total por trade de la mejor
cuenta cent disponible es **>20 % peor** que el actual, se descarta — con la comisión
siendo ~87 % del drag, la granularidad no compra nada si el costo sube.

## Lo medido

**Costo actual (ICMarkets Raw Spread, verificado en vivo 19-ago)**: spread 0,0-0,1p
(el tick de hoy: 1 point) + comisión ~$7/lote ida-vuelta ≈ 0,7p ⇒ **all-in ~0,8p**.

| Opción | Estructura | All-in EURUSD estimado | vs actual |
|---|---|---|---|
| **IC Markets cent** | **No existe** — IC Markets no ofrece cuenta cent | — | — |
| Exness Standard Cent | Sin comisión; spread del Standard es 0,9p y el Cent es **más ancho** ("spreads will be wider than with other accounts", doc oficial) | ≥1,0-1,5p | **+25 a +90 %** ❌ |
| RoboForex ProCent | Sin comisión, pricing tipo Pro (1,4p) | ~1,3-1,5p | **+60 a +90 %** ❌ |
| FBS Cent | Sin comisión, spread markup | similar | ❌ |
| Cent + raw spread + comisión | **No existe en el mercado**: las cuentas cent son productos de spread markup para principiantes; ningún bróker relevado combina denominación cent con pricing raw/ECN | — | — |

## Veredicto

**Descartada.** Ninguna opción pasa el gate: el peaje es +0,3 a +0,7p **por trade**, en
un sistema donde el diagnóstico estructural es que la fricción ya se come el edge (el
research del 19-ago: 14/14 familias de señal intradía con edge bruto DEBAJO de 2 pts de
fricción). Pagar más fricción para ganar granularidad de sizing es cambiar el problema
grande por el chico.

**Lo que esto deja en claro** (y conviene escribir para no reabrirlo):
- Los 4 cuellos (Kelly, meta-labeling, D1 activo, salidas parciales) **dependen del
  CAPITAL de verdad**, no del tipo de cuenta. La única palanca real es depositar más
  (o el crecimiento de la propia cuenta). A ~$2.500-3.000, el lote 0,01 pasa a ser
  ~1/4 del sizing del 1 % con SL de 15p ⇒ aparecen 3-4 escalones de modulación sin
  cambiar de bróker ni de costo.
- **Opcional de valor bajo**: una demo cent (Exness/RoboForex) sigue siendo un sandbox
  gratis para DESARROLLAR el código de sizing variable antes de que el capital exista.
  Pero desarrollar código para una condición que no se sabe cuándo llega viola el
  principio rector (un fix que no arregla nada, empeora). No hacer.

## Fuentes

- [Standard Cent account — Exness Help Center](https://get.exness.help/hc/en-us/articles/17537782786588-Standard-Cent-account)
- [Best IC Markets Alternatives 2026 — BrokerAnalysis](https://www.brokeranalysis.com/ic-markets-alternatives/)
- [Exness vs IC Markets — CompareForexBrokers](https://www.compareforexbrokers.com/reviews/exness-vs-ic-markets/)
- [10 Best Forex Brokers with Cent Accounts — FXLeaders](https://www.fxleaders.com/forex-brokers/forex-brokers-with-cent-accounts/)
- [Forex Brokers with Raw Spread Accounts — Tradingpedia](https://www.tradingpedia.com/forex-brokers/forex-brokers-with-raw-spread-accounts/)
- [RAW/ECN Account Spread Testing — CompareForexBrokers](https://www.compareforexbrokers.com/our-methodology/forex-fees/tightest-spreads/)
