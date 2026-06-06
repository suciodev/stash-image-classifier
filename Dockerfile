FROM python:3.12-slim

# Runtime libs for opencv-python-headless and PyTorch OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install the venv at /opt/venv so a bind-mounted /app doesn't shadow it
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install deps before copying source for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

CMD ["uv", "run", "pytest", "-v"]
