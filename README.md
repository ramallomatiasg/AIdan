# Financial News Monitoring Agent

Un agente inteligente que monitorea feeds de noticias financieras, detecta eventos económicos importantes, calcula su impacto y envía alertas automáticas.

## 📋 Características

- **Collector**: Fetch automático de feeds RSS de múltiples fuentes (FT, Reuters, Bloomberg, etc.)
- **Analyzer**: Análisis de impacto con scoring 0-100 y detección de entidades/tags
- **Admin API**: Dashboard REST con FastAPI para ver estadísticas, alertas y noticias recientes
- **Database**: SQLite para persistencia (noticias, alertas, errores)
- **Telegram Alerts**: Notificaciones automáticas con nivel [ALTA/MEDIA/BAJA]
- **Data Cleanup**: Limpieza automática de datos antiguos (default: 72h)

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────┐
│     Collector (cada 10-15 min)          │
│   - Fetch RSS feeds                     │
│   - Normalizar noticias (HTML → JSON)   │
│   - Detectar idioma y entidades         │
│   - Guardar a BD + archivos JSONL       │
└──────────────────┬──────────────────────┘
                   │
┌─────────────────────────────────────────┐
│     Analyzer (cada 2 min)               │
│   - Leer noticias sin procesar          │
│   - Calcular score de impacto (0-100)   │
│   - Generar resúmenes                   │
│   - Enviar alertas Telegram             │
└──────────────────┬──────────────────────┘
                   │
┌─────────────────────────────────────────┐
│     Admin API (FastAPI :8000)           │
│   - /health                             │
│   - /stats (estadísticas)               │
│   - /recent-alerts (últimas 50)         │
│   - /recent-news (últimas 200)          │
└─────────────────────────────────────────┘
```

## 📁 Estructura del Proyecto

```
AIdan/
├── src/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── config.py          # Config general (env vars)
│   │   ├── logging_setup.py   # Logging con JSON
│   │   └── db.py              # SQLite utilities
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── feed_fetcher.py    # Fetch + parseo de RSS
│   │   └── main.py            # Loop principal del collector
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── news_analyzer.py   # Cálculo de impacto
│   │   └── main.py            # Loop principal del analyzer
│   └── admin/
│       ├── __init__.py
│       └── main.py            # API FastAPI
├── config/
│   └── sources.yaml           # Lista de feeds RSS
├── scripts/
│   ├── run_collector.bat/.sh
│   ├── run_analyzer.bat/.sh
│   └── run_admin.bat/.sh
├── data/                      # JSONL files por hora (YYYY/MM/DD/HH/news.jsonl)
├── state/                     # SQLite database
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── Dockerfile                 # Admin service
└── README.md
```

## 🚀 Instalación y Ejecución

### Opción 1: Con Python local

#### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

#### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tus valores (tokens Telegram, etc.)
```

#### 3. Correr servicios en terminales separadas

Terminal 1 - Collector:
```bash
python src/collector/main.py
```

Terminal 2 - Analyzer:
```bash
python src/analyzer/main.py
```

Terminal 3 - Admin API:
```bash
python src/admin/main.py
```

Luego acceder a: http://localhost:8000/docs

### Opción 2: Con Docker Compose

```bash
docker compose up --build
```

Acceder a: http://localhost:8000/docs

### Opción 3: Demo rápida

```bash
python demo.py
```

Esto ejecuta un demo con datos de prueba y muestra estadísticas.

## ⚙️ Configuración

### .env
```
TELEGRAM_TOKEN=tu_bot_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
COLLECTOR_INTERVAL=600          # 10 minutos
ANALYZER_INTERVAL=120           # 2 minutos
DATA_RETENTION_HOURS=72
LOG_LEVEL=INFO
```

### config/sources.yaml
```yaml
sources:
  - name: "Financial Times"
    url: "https://feeds.ft.com/markets"
  - name: "Reuters"
    url: "https://feeds.reuters.com/reuters/businessNews"
  # ... más fuentes
```

## 📊 API Endpoints

### Health Check
```bash
GET /health
```

Respuesta:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-25T10:30:00"
}
```

### Estadísticas
```bash
GET /stats
```

Respuesta:
```json
{
  "status": "success",
  "data": {
    "total_news": 1250,
    "total_alerts": 45,
    "news_last_hour": 12
  }
}
```

### Alertas Recientes
```bash
GET /recent-alerts?limit=50
```

Respuesta:
```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "id": 42,
      "impact_score": 88,
      "sent_at": "2026-02-25T10:15:00",
      "title": "Federal Reserve Raises Interest Rates...",
      "url": "https://...",
      "level": "ALTA"
    }
  ]
}
```

### Noticias Recientes
```bash
GET /recent-news?limit=200
```

## 📈 Lógica de Scoring

El analyzer calcula impact_score (0-100) considerando:

1. **Keywords de Alto Impacto** (+30 puntos máx):
   - "fed", "interest rate", "recession", "crash", "emergency", etc.

2. **Keywords de Medio Impacto** (+20 puntos máx):
   - "market", "stock", "earnings", "analyst", etc.

3. **Entidades Detectadas** (+15 puntos máx):
   - FED, ECB, Powell, CPI, GDP, S&P500, Nasdaq, DOW

4. **Tags** (+10 puntos cada una):
   - `monetary_policy`, `market_volatility`, `earnings`, `merger`, `crypto`, `tech`, `energy`, `geopolitics`

5. **Breaking News** (+20 puntos):
   - Si contiene "breaking", "alert", "emergency", "urgent"

**Niveles de Alerta:**
- **ALTA**: score ≥ 80
- **MEDIA**: 50 ≤ score < 80
- **BAJA**: score < 50 (sin alerta)

## 🔧 Desarrollo

### Estructura de módulos

**common/config.py**: Configuración centralizada desde variables de entorno.

**common/db.py**: Operaciones SQLite (news, alerts, errors tables).

**collector/feed_fetcher.py**: Descarga RSS con feedparser + parsing HTML con BeautifulSoup.

**analyzer/news_analyzer.py**: Scoring, detección de entidades, generación de resúmenes.

**admin/main.py**: API REST con FastAPI para el dashboard.

### Extensiones futuras

- [ ] Integración real con Telegram Bot API
- [ ] Machine Learning para scoring dinámico
- [ ] Más fuentes de noticias (APIs REST además de RSS)
- [ ] Caché distribuido (Redis)
- [ ] Autenticación en API
- [ ] Frontend React para dashboard
- [ ] Webhooks para notificaciones externas
- [ ] Análisis de sentimiento

## 📝 Logging

Todos los componentes usan logging estructurado en JSON:

```json
{
  "timestamp": "2026-02-25T10:30:00.123456",
  "level": "INFO",
  "logger": "collector.main",
  "message": "Fetched 5 news items"
}
```

## 🐛 Troubleshooting

### Port 8000 ya está en uso
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

### Database locked
```bash
rm state/financial_news.db
# Se recrea automáticamente
```

### Feeds no se cargan
- Revisar archivo `config/sources.yaml`
- Verificar conexión a internet
- Chequear logs en `state/`

## 📄 Licencia

MIT License

## 👨‍💻 Autor

Creado como demostración de agente de monitoreo de noticias financieras con Python.

---

**Nota**: Este proyecto es una demostración educativa. Para uso en producción, se recomiendan mejoras en seguridad, escalabilidad y manejo de errores.
   ```bash
   docker-compose down
   ```

## Testing

To run tests, you can use pytest:
```bash
pytest
```

## Usage
- The collector runs every 10 minutes.
- The analyzer runs every 2 minutes or when new files are detected.
- The janitor cleans up old data every hour.

## Endpoints
- `/health`: Check service health.
- `/stats`: Get statistics on news and alerts.
- `/recent-alerts`: Get the latest alerts.
- `/recent-news`: Get the latest news items.

## Logging
Structured logging in JSON format is implemented throughout the services.

## Contributing
Feel free to submit issues and pull requests!