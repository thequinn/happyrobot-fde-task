FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets $PORT; default to 8080 locally
ENV PORT=8000

# Expose for local dev (Cloud Run ignores EXPOSE)
EXPOSE 8000

# Start server
CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
