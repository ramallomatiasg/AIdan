# Dockerfile for Analyzer Service
FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/analyzer ./analyzer

CMD ["python", "-m", "analyzer.main"]
