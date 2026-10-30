FROM python:3.11-slim

WORKDIR /app

# install deps first so Docker layer caching keeps rebuilds fast
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "src/pipeline.py"]
