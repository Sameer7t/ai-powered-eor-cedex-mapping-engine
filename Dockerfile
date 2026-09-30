# ============================================================
# AI-Powered EOR Processing & CEDEX Mapping Engine
# Production Docker Container for Render / Cloud Deployment
# ============================================================

FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies if required (e.g. for pdfplumber / fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and reference mappings
COPY src/ ./src/
COPY data/ ./data/
COPY mappings/ ./mappings/
COPY samples/ ./samples/

# Create output directory for generated Excel reports
RUN mkdir -p data/output src/mappings

EXPOSE 8000

# Health check against FastAPI endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Launch production server via Uvicorn with dynamic cloud PORT binding
CMD ["sh", "-c", "python -m uvicorn src.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
