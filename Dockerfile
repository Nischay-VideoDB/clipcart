FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV CLIPCART_DATA_DIR=/data
EXPOSE 5000

CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 4 --bind 0.0.0.0:${PORT:-5000} web.server:app"]
