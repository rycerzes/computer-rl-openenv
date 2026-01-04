FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    xvfb \
    git \
    build-essential \
    linux-libc-dev \
    python3-tk \
    dos2unix \
    xfce4 \
    xfce4-terminal \
    firefox-esr \
    libreoffice-writer \
    libreoffice-calc \
    wmctrl \
    xdotool \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN mkdir -p /workspace

COPY uv.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev

COPY . ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

COPY environments/computer_rl_env/server/start.sh /usr/local/bin/
RUN dos2unix /usr/local/bin/start.sh && chmod +x /usr/local/bin/start.sh

CMD ["start.sh"]