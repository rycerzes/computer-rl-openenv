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
    python3-lxml \
    python3-pyatspi \
    at-spi2-core \
    ffmpeg \
    scrot \
    x11-utils \
    dconf-cli \
    xauth

# Install Google Chrome
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux-signing-key.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# Install VS Code
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y google-chrome-stable code

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