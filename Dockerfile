FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /home/output

ENV PORT=8000
EXPOSE 8000

CMD gunicorn --bind=0.0.0.0:${PORT} --workers=1 --threads=4 --timeout=1800 --access-logfile=- webapp:app
