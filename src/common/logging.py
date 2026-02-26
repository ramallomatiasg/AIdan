# common/logging.py
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {"level": record.levelname, "message": record.msg}
        return json.dumps(log_obj)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers[0].setFormatter(JsonFormatter())
