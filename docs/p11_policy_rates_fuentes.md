# P11 — tasas de política a fin de mes: fuentes

Archivo: `docs/p11_policy_rates.csv` (83 filas, 2019-11 → 2026-09). Valor = tasa vigente el último día
calendario del mes; un cambio cuenta en el mes cuya fecha de fin es >= la fecha EFECTIVA (no la del anuncio).
Armado el 23-oct-2026.

## Fuentes por moneda
- **USD** (punto medio del rango de fed funds): tabla oficial de la Fed, federalreserve.gov/monetarypolicy/openmarket.htm (fechas efectivas, incluye el +25 del 17-sep-2026 a 3,75-4,00).
- **EUR** (tasa de depósito): tabla oficial del BCE, ecb.europa.eu, key ECB interest rates (incluye las subas del 17-jun-2026 a 2,25 y del 16-sep-2026 a 2,50).
- **GBP** (Bank Rate): base oficial del BoE, bankofengland.co.uk/boeapps/database/Bank-Rate.asp (último cambio 18-dic-2025, 3,75); hold de sep-2026 confirmado por búsqueda (voto 6-3).
- **JPY**: comunicados del BoJ (boj.or.jp, k240731a: el 0,25 rige desde el 1-ago-2024; k260918a: 1,25 rige desde el 24-sep-2026) + notas de prensa para dic-2025 (0,75) y 16-jun-2026 (1,00). Rango 0-0,1 de mar-2024 cargado como 0,05.
- **AUD**: tabla oficial del RBA, rba.gov.au/statistics/cash-rate (fechas efectivas; subas 2026 en feb, mar, may y 30-sep a 4,60).
- **NZD**: global-rates.com (RBNZ, oct-2024 → sep-2026) + calculate.co.nz (historia 2020-2026). rbnz.govt.nz devolvió 403.
- **CAD**: página oficial del BoC (bankofcanada.ca, decisiones abr-2025 → sep-2026: 2,25 sin cambios en 2026) + búsqueda/Scotiabank para 2020-2024.
- **CHF**: global-rates.com (SNB, sep-2022 → jun-2025) + snb.ch (fechas de evaluación) + búsqueda para el hold del 24-sep-2026 (0%).

## Meses arrastrados o con duda
- Ningún mes quedó arrastrado sin verificar: todas las monedas tienen fuente para sep-2026.
- **JPY 2024-07 = 0,05** (no 0,25): la suba se decidió el 31-jul-2024 pero rige desde el 1-ago-2024 (comunicado del BoJ). Si se prefiere la fecha de anuncio, cambiar a 0,25.
- **NZD 2025-05 = 3,25**: global-rates pone el recorte el 28-may-2025; calculate.co.nz lo ubica en jul-2025 (contradicción interna de esa página). Se usó 3,25 (coincide con lo que recuerdo del 28-may).
- **NZD 2022 (feb-oct) y CAD jul-dic-2022**: fechas exactas de cada suba no las mostró ninguna fuente fetcheada; se cargaron de memoria, consistentes con los niveles de fin de año que sí se verificaron. Nivel a fin de mes de baja duda.
- **NZD sep-2026 = 2,75**: suba del 2-sep-2026 con dos fuentes secundarias (global-rates, calculate.co.nz), no con el sitio del RBNZ.
- **JPY dic-2025 = 0,75**: sin comunicado del BoJ leído; lo confirman notas de prensa de jun-2026 ("primera suba desde dic-2025").
