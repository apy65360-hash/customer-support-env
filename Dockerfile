# Customer Support OpenEnv — Dockerfile
# Targets HuggingFace Spaces (port 7860) and local Docker runs.
FROM python:3.11-slim

# Keeps Python from generating .pyc files and enables unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# HuggingFace Spaces expects the service on port 7860
EXPOSE 7860

# Run the FastAPI app with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
