"""
logging_setup.py — Logger unico de AIdan: consola + archivo rotativo.

Por que existe el file handler (auditoria 31 Jul 2026): AIdan NO persistia logs.
El "incidente 14 Jun" (proceso caido) quedo con causa NO DETERMINABLE justamente
por eso, y con 189 bloques `except` que fallan en silencio, no tener logs en disco
hace que cada incidente sea irrecuperable por construccion.

Los logs van a %APPDATA%/AIdan/logs/aidan.log, 10 MB x 5 archivos (50 MB tope).
Formato de archivo: texto plano con timestamp AR (para leerlo a ojo durante un
forense). Consola: JSON, como antes (no se rompe nada que parsee stdout).
"""
import logging
import logging.handlers
import json
import os
from datetime import datetime, timedelta, timezone

TZ_AR = timezone(timedelta(hours=-3))

LOG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'aidan.log')
MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))   # 10 MB
BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))               # 5 archivos

_FILE_HANDLER = None


class JSONFormatter(logging.Formatter):
    """Formato de consola — igual que antes, para no romper nada aguas abajo."""
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(TZ_AR).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


class ARFormatter(logging.Formatter):
    """Formato de archivo — texto plano en hora AR, legible en un forense."""
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, TZ_AR).strftime('%Y-%m-%d %H:%M:%S')


def install_file_logging(level="INFO"):
    """Engancha el RotatingFileHandler al logger ROOT (una sola vez).

    Va al root a proposito: asi caen al archivo TAMBIEN los loggers que nunca
    pasan por setup_logging (`db`, `confidence_predictor`, `mt5_executor`,
    `change_manager`...), que son justo los que loguean los errores mudos.
    Los loggers con nombre solo llevan su StreamHandler y propagan al root
    => consola 1 vez, archivo 1 vez, sin duplicados.
    """
    global _FILE_HANDLER
    if _FILE_HANDLER is not None:
        return _FILE_HANDLER
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding='utf-8', delay=True,
        )
        h.setFormatter(ARFormatter(
            '%(asctime)s %(levelname)-7s %(name)-12s %(message)s'
        ))
        root = logging.getLogger()
        root.addHandler(h)
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(level)

        # Callar librerias charlatanas: al colgar el handler del ROOT, su INFO
        # tambien cae al archivo. httpx loguea CADA request y AIdan hace llamadas
        # todo el tiempo (feeds, Groq, MT5) -> ahogaria justo lo que se busca en
        # un forense. Sus WARNING/ERROR siguen entrando, que es lo que importa.
        for _noisy in ('httpx', 'httpcore', 'urllib3', 'urllib3.connectionpool',
                       'requests', 'asyncio', 'PIL', 'matplotlib', 'watchfiles',
                       'multipart', 'python_multipart'):
            logging.getLogger(_noisy).setLevel(logging.WARNING)

        _FILE_HANDLER = h
    except Exception:
        # Si el disco/permisos fallan, seguimos con consola sola. Nunca tumbar
        # el arranque de AIdan por un problema de logging.
        _FILE_HANDLER = False
    return _FILE_HANDLER


def setup_logging(name, level="INFO"):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    install_file_logging(level)

    # Idempotente: si ya lo configuramos, no apilar handlers duplicados
    # (antes cada llamada agregaba otro StreamHandler -> lineas repetidas).
    if getattr(logger, '_aidan_configured', False):
        return logger

    stream = logging.StreamHandler()
    stream.setFormatter(JSONFormatter())
    logger.addHandler(stream)

    logger._aidan_configured = True
    return logger


def get_log_path():
    """Para el dashboard / diagnostico: donde estan los logs."""
    return LOG_FILE
