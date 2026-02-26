# Dockerfile for Admin Service
FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/admin ./admin

CMD ["uvicorn", "admin.main:app", "--host", "0.0.0.0", "--port", "8000"]
