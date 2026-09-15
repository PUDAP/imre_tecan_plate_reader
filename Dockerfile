FROM python:3.13-slim-bookworm

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install build tools and the Linux libusb runtime used by PyUSB.
RUN apt-get update && apt-get install -y \
  build-essential \
  libusb-1.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY . .

CMD ["uv", "run", "python", "main.py"]
