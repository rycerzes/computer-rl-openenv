FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y \
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
    libreoffice-impress \
    vlc \
    gimp \
    thunderbird \
    wmctrl \
    xdotool \
    supervisor \
    dbus \
    dbus-x11 \
    curl \
    wget \
    gnupg \
    software-properties-common \
    gobject-introspection \
    libgirepository1.0-dev \
    libcairo2-dev \
    pkg-config \
    python3-lxml \
    python3-pyatspi \
    at-spi2-core \
    ffmpeg \
    scrot \
    x11-utils \
    dconf-cli \
    xauth

# Install Chrome for Testing (pinned, reproducible, no auto-update)
# See https://developer.chrome.com/blog/chrome-for-testing
ARG CHROME_VERSION=145.0.7632.117
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends unzip \
    # Shared libraries Chrome needs (normally pulled by the .deb package)
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcairo2 libcups2 \
    libdbus-1-3 libdrm2 libexpat1 libgbm1 libglib2.0-0 libnspr4 \
    libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
    fonts-liberation \
    && curl -fsSL "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
       -o /tmp/chrome.zip \
    && unzip /tmp/chrome.zip -d /opt/chrome-for-testing \
    && ln -s /opt/chrome-for-testing/chrome-linux64/chrome /usr/local/bin/chrome \
    && ln -s /usr/local/bin/chrome /usr/local/bin/google-chrome-stable \
    && ln -s /usr/local/bin/chrome /usr/local/bin/google-chrome \
    && rm /tmp/chrome.zip

# Install VS Code
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y code

# Clean up power management packages to prevent blanking
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get remove -y xfce4-power-manager xfce4-screensaver light-locker xscreensaver-data || true

ENV DISPLAY=:99
ENV GTK_MODULES=gail:atk-bridge
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
EXPOSE 1337

COPY environments/computer_rl_env/server/start.sh /usr/local/bin/
RUN dos2unix /usr/local/bin/start.sh && chmod +x /usr/local/bin/start.sh

CMD ["start.sh"]