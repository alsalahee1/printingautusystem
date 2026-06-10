# PrintSys — offset-printing management system
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRINTSYS_DB_URL=sqlite:////data/printsys.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite database lives on a mounted volume so it survives container restarts.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Tables, the admin user and the chart of accounts are created on startup.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
