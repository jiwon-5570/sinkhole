FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SINKHOLE_HOST=0.0.0.0
ENV SINKHOLE_RELOAD=0
ENV PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY scripts ./scripts
COPY .env.example ./.env.example

EXPOSE 8080

CMD ["python", "-m", "app.main"]
