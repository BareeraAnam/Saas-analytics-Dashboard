FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Daphne serves HTTP and the metrics websocket.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
