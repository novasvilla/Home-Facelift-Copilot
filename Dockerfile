# Multi-stage build: frontend + backend
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Backend runtime
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy backend dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy backend code
COPY app/ ./app/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create static and uploads directories
RUN mkdir -p static uploads

# Expose port
ENV PORT=8080
EXPOSE 8080

# Run ADK server
CMD ["uv", "run", "adk", "api_server", ".", "--port", "8080", "--host", "0.0.0.0"]
