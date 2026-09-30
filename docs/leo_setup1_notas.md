# Setup 1 de Leo — transcripción (29 Sep 2026)

Fuente: WhatsApp de Leo al user, 29-sep, con 5 capturas de TradingView (EURUSD). Los audios eran
de otro tema. **Todavía NO es un criterio de prueba:** es la materia prima. Las reglas mecánicas se
le mandaron a Leo para que las confirme ANTES de medir (para que las definiciones no las elija yo
viendo resultados).

## Lo que escribió (resumido, sus términos)

1. **H4 — direccionalidad mayor.** Alcista o bajista según las últimas rupturas: si hizo un máximo
   más alto o un mínimo más bajo.
2. **H1 — replica.** Últimas rupturas y dirección; además zonas de **liquidez o imbalance**
   importantes y **recientes** ("no un imbalance de hace 5 horas"). **El BOS tiene que ser con
   cuerpo de vela, no con mecha** (fuerza, no búsqueda de liquidez).
3. **M15 — zonas.** Liquidez y oferta/demanda. En bajista el precio tiene que volver a zonas de
   oferta. Marca la zona **"decisional"** (último punto donde el precio decidió romper el mín/máx
   anterior) y el **"extremo"** (origen del movimiento general, donde hay más fuerza). La
   decisional muchas veces no se respeta; **él elegiría operar en el extremo de M15**.
4. **M5 — entrada.** Agresiva: orden lista en la zona (arriesgado, siempre hay liquidez por
   encima). **Conservadora:** esperar que el precio entre a la zona, ver el rechazo y un **CHoCH**
   (cambio de estructura), y ahí entrar. **TP = los mínimos a romper: mínimo de M15, de H1 y de H4.**
5. Tener en cuenta **el horario** de los movimientos junto con las **noticias** del día.

## Lo que muestran las capturas
- H4 y H1 bajistas con BOS marcados; máximos/mínimos de H4 y H1 señalados.
- M15: zona "M15" arriba (el extremo, junto al máximo de H1) y "M15 pero decisional" más abajo.
- M5: ejemplo de venta con **SL 5,0 pips / TP 16,8 pips (R:R 3,36)** desde una zona de M5.
- Proyección: venta en el extremo de M15, objetivos mínimo M15 → mínimo H4 → mínimo H1.

## Pendiente de Leo (preguntas enviadas el 29-sep)
Coincidencia H4/H1 · qué zona opera (extremo o ambas) · antigüedad máxima de una zona · definición
exacta del CHoCH de entrada · dónde va el SL y con cuánto margen · reparto de los 3 TP y si mueve a
break-even · cuándo se anula el plan · ventana de noticias y horarios a evitar.

## Contexto
AIdan ya tiene un track `smc` (`src/analyzer/smc.py`: bias HTF + zona + BOS en M5) con 42 trades,
38% ganados, −$13,99 lifetime, **nunca probado con años de datos**. El de Leo es una versión más
precisa (BOS con cuerpo, extremo vs decisional, CHoCH, TP en mínimos estructurales).
