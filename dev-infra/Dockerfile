# Dev image for local plugin testing. Safe copy of the production Dockerfile.
# Does NOT affect your stash-git image or any running containers.
#
# Uses python:3.12-slim (Debian/glibc) instead of the upstream Alpine stash image.
# The official stash-linux binary is statically linked (no DT_NEEDED entries),
# so it runs on any x86-64 Linux kernel unchanged.
#
# Switching to glibc eliminates all musl compatibility patches previously required:
#   - no gcompat
#   - no libgomp swap (torch ships glibc wheels; they just work)
#   - no fake opencv dist-infos
#   - no LD_PRELOAD / __res_init stub
#   - no .gnu.so → .musl.so symlinks
#
# Build via Makefile: make start-dev

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    libvips-tools \
    ruby \
    git \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Stash binary (statically linked — no glibc/musl dependency)
RUN curl -fsSL https://github.com/stashapp/stash/releases/download/v0.31.1/stash-linux \
    -o /usr/local/bin/stash && chmod +x /usr/local/bin/stash

RUN gem install faraday

RUN pip install --no-cache-dir \
    requests \
    requests-toolbelt \
    lxml \
    mechanicalsoup \
    cloudscraper \
    stashapp-tools \
    google-api-python-client \
    Pillow \
    ultralytics \
    opencv-python-headless

# python:3.12-slim already provides /usr/local/bin/python; also add /usr/bin/python
# so the plugin manifest (exec: python main.py) resolves under both PATH layouts.
RUN ln -sf /usr/local/bin/python3 /usr/bin/python

EXPOSE 9995
ENTRYPOINT ["/usr/local/bin/stash"]
