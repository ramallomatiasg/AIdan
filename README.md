# AIdan v1.3 - Asistente de Scalping EUR/USD con IA

Sistema que monitorea noticias financieras en tiempo real y genera senales de trading para EUR/USD usando inteligencia artificial local. Todo corre en tu PC, sin pagar APIs ni suscripciones.

**Un solo ejecutable de 25MB - Portable, gratis y privado.**

---

## Como funciona (en simple)

AIdan hace 3 cosas en automatico cada 10 minutos:

1. **Busca noticias** en Bloomberg, Reuters, Financial Times y otras fuentes financieras
2. **Las analiza con IA** (Ollama corriendo en tu PC) y decide si afectan o no al EUR/USD
3. **Te muestra todo** en un dashboard web con graficos, alertas y un chat para consultar

Vos solo tenes que abrir AIdan.exe, esperar 30 segundos, y se abre el navegador con todo listo.

---

## Instalacion

### Usuarios (lo mas facil)

1. Descomprime `AIdan_Portable.rar`
2. Ejecuta `AIdan.exe`
3. La primera vez descarga 2 modelos de IA (~8GB total) - tarda 10-15 min segun tu internet
4. Listo. Se abre solo en el navegador

**Requisitos:**
- Windows 10/11
- 8GB de RAM minimo (16GB recomendado)
- 10GB de disco libre (para los modelos de IA)
- Conexion a internet

### Desarrolladores

```
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan
pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull llava
python AIdan_TodoEnUno.py
```

---

## Que ves en el Dashboard

Cuando abris AIdan se muestra un dashboard web con dos pestanas principales: **Dashboard** y **Estrategias**.

### Barra superior (siempre visible)

La barra de arriba se queda fija cuando scrolleas. Muestra:

- **AIdan / SCALPING EUR/USD** - nombre del sistema
- **Reloj** - hora actual en tu zona horaria
- **Activo** (verde) - indica que todos los servicios estan corriendo
- **Luna/Sol** - cambia entre modo oscuro y claro

Debajo hay chips con estadisticas rapidas:

- **NOTICIAS** - cuantas noticias recolecto hoy
- **ALERTAS** - cuantas alertas genero hoy la IA
- **ULTIMA HORA** - alertas de los ultimos 60 minutos
- **WIN RATE** - porcentaje de exito de las estrategias que marcaste
- **HISTORIAL** - cuantas estrategias acertaron (W) y cuantas fallaron (L)

---

### Pestana DASHBOARD

Esta es la pantalla principal con 4 secciones:

#### Grafico EUR/USD (arriba izquierda)

Un grafico de velas en tiempo real de TradingView. Muestra el par EUR/USD en velas de 5 minutos con indicadores tecnicos:

- **MA 9** (media movil) - linea que sigue el precio
- **Bollinger Bands** - bandas que muestran volatilidad
- **RSI** - indicador abajo que muestra si esta sobrecomprado (>70) o sobrevendido (<30)
- **Volumen** - barras de volumen

Podes cambiar el timeframe (1m, 5m, 15m, 1h) y agregar mas indicadores.

#### Chat AIdan (arriba derecha)

Un chat donde podes hablar con la IA sobre trading. Le podes preguntar:

- "Deberia operar ahora?"
- "Como ves el mercado?"
- "Que dicen las noticias?"

**Podes adjuntar imagenes** (capturas de graficos) con el boton de clip y la IA las analiza para darte su opinion sobre la estrategia que ves en el grafico.

La IA usa datos del grafico actual + noticias recientes + alertas activas para darte respuestas contextualizadas para scalping.

#### Alertas de Trading (centro)

Aca aparecen las noticias que la IA analizo y considero relevantes para EUR/USD. Solo muestra alertas del dia actual.

Cada alerta tiene:

- **Direccion**: CALL (sube), PUT (baja), o NEUTRAL
- **Confianza**: que tan segura esta la IA de la direccion (0-100%)
- **Score**: que tan importante es la noticia para forex (0-100)
- **Linea de accion**: dice claramente OPERAR o NO OPERAR con la razon
- **Titulo de la noticia** (clickeable para leer la fuente original)

**Filtros disponibles:**
- Direccion (Todas / CALL / PUT)
- Confianza minima (slider 0-100%)
- Periodo (Todo / 1h / 6h / 24h)

**Botones Win / Loss / Skip:**
- **Win** = la senal acerto (el precio fue en la direccion indicada)
- **Loss** = la senal fallo (el precio fue en la direccion contraria)
- **Skip** = no operaste esa senal
- Estos datos se usan para calcular el Win Rate y mejorar las recomendaciones

#### Calendario Economico (abajo)

Muestra los eventos economicos de la semana que afectan a EUR/USD (datos de Investing.com). Solo muestra eventos de impacto medio y alto para USD y EUR.

Cada evento tiene:
- Hora del evento
- Divisa afectada (USD o EUR)
- Importancia (iconos de toro)
- Dato actual vs prevision vs anterior

Los eventos con datos que sorprenden al mercado (muy diferentes a la prevision) suelen generar movimientos fuertes en el precio.

#### Ticker de noticias (barra inferior)

Una barra que scrollea con las ultimas noticias recolectadas. Clickea cualquiera para leer la fuente.

---

### Pestana ESTRATEGIAS

Aca se generan y muestran las estrategias de trading automaticas.

#### Estrategias Auto-Generadas (arriba)

Cuando llega una noticia de alto impacto (score >= 75, confianza >= 65, con direccion clara), AIdan genera automaticamente una estrategia con:

- **Grafico de velas** mostrando la zona de operacion con Entry, Take Profit (TP) y Stop Loss (SL) marcados
- **Direccion** (CALL o PUT) con flecha visual
- **Precio de entrada, TP y SL** exactos
- **Hora de la senal** y titulo de la noticia que la genero
- **Estado**: ACTIVA (dentro de los 5 min de expiración) o EXPIRADA

**Reglas de las estrategias:**
- Solo se generan con noticias frescas (menos de 10 minutos)
- Se guardan maximo 6 - las mas viejas se descartan automaticamente
- Expiran a los 5 minutos (scalping de corto plazo)

**Botones Win / Loss / Skip** (en cada estrategia):
- Marca si la estrategia acerto o fallo
- Esto alimenta el Win Rate y el historial W/L de la barra superior
- AIdan aprende de estos resultados para calibrar sus futuras recomendaciones

#### Parametros de estrategias automaticas (abajo, colapsable)

Aca configuras los filtros que AIdan usa para decidir cuando generar una estrategia. Podes crear "perfiles" con distintas configuraciones:

**Filtros de entrada:**
- Impact score minimo (0-100) - que tan relevante tiene que ser la noticia
- Confianza minima % (0-100) - que tan segura tiene que estar la IA
- Direccion permitida (CALL y PUT / Solo CALL / Solo PUT)

**Gestion de riesgo:**
- Stop Loss en pips (distancia del SL al entry)
- Take Profit en pips (distancia del TP al entry)
- Expiracion en minutos

**Perfiles guardados:**
Podes guardar varias configuraciones con nombres descriptivos (ej: "Conservador", "Agresivo", "Solo CALL") y switchear entre ellas.

---

## Como interpretar las senales

### Cuando OPERAR

La IA recomienda operar solo cuando se dan estas condiciones juntas:

1. Noticia de alto impacto (datos macro: NFP, CPI, tasas de interes, PIB)
2. Score >= 75
3. Confianza >= 65%
4. Direccion clara (CALL o PUT, no NEUTRAL)
5. El analisis tecnico no contradice la senal fundamental

### Cuando NO OPERAR

- Noticias corporativas (fusiones, IPOs, earnings) - no mueven forex
- Geopolitica sin dato economico concreto - direccion ambigua
- Confianza baja (<65%) - la IA no esta segura
- Score bajo (<75) - la noticia no es relevante para EUR/USD
- Momentum tecnico contradice la senal de noticias

### Senales de la IA vs realidad

Las noticias tienen un impacto INMEDIATO en el mercado (primeros 1-5 minutos). Por eso:

- Las estrategias solo se generan con noticias de menos de 10 minutos
- Las estrategias expiran a los 5 minutos
- No sirve operar una noticia vieja - el mercado ya la precio

---

## Arquitectura tecnica

```
AIdan.exe (25MB)
  |
  +-- Collector (thread) --> Busca noticias RSS cada 10 min
  |     Bloomberg, Reuters, Financial Times, etc.
  |
  +-- Analyzer (thread) --> Analiza con Ollama cada 60 seg
  |     llama3.1:8b (texto) + llava (imagenes)
  |     + TechnicalAnalyzer (datos de Yahoo Finance)
  |
  +-- API (thread) --> Servidor web en localhost:8000
        FastAPI + Dashboard HTML
        Chat con IA + Graficos TradingView
```

**Modelos de IA usados:**
- `llama3.1:8b` (~4GB) - analisis de noticias y chat de texto
- `llava` (~4GB) - analisis de imagenes/graficos en el chat

Ambos corren 100% local con Ollama. No se envia nada a la nube.

---

## Crear ejecutable

```
pyinstaller AIdan_TodoEnUno.spec --clean
```

Para empaquetar:
```
crear_paquete.bat
```

Resultado: `AIdan_Portable.rar` (~25MB)

---

## Historial de versiones

### v1.3 (18 Mar 2026)
- Pestana "Estrategias" con graficos de velas auto-generados (Entry/SL/TP visual)
- Estrategias automaticas al detectar noticias de alto impacto (<10 min)
- Analisis tecnico integrado (tendencia, RSI, volumen) cruza con noticias
- Chat con IA acepta imagenes de graficos (modelo llava)
- Prompt de analisis mejorado: scores variados y descripciones cortas
- Header y tabs sticky al scrollear
- Alertas solo del dia actual
- Timestamps en hora local (ya no UTC)
- Perfiles de configuracion guardables (Conservador, Agresivo, etc.)
- Calendario economico filtrado solo EUR/USD
- Descarga automatica de llava al primer inicio
- Win/Loss/Skip en estrategias para trackear efectividad

### v1.2 (02 Mar 2026)
- Dashboard con grafico TradingView en vivo
- Alertas con filtros (direccion, confianza, periodo)
- Chat con IA para consultas de scalping
- Calendario economico de Investing.com
- Ticker de noticias en barra inferior
- Modo oscuro/claro
- Ejecutable portable todo-en-uno (23MB)

### v1.1
- Analisis con Ollama/Llama 3.1
- Alertas basicas de noticias
- API + dashboard web

### v1.0
- Recolector RSS de noticias financieras
- Analisis por keywords
- Dashboard minimo

---

## Licencia

MIT - Uso libre.

## Disclaimer

AIdan es una herramienta de asistencia, NO un sistema de trading automatico. Las senales son orientativas y no garantizan resultados. Opera bajo tu propio riesgo y criterio. Nunca arriesgues dinero que no puedas perder.
