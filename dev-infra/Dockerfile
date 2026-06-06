# Dev image for local plugin testing. Safe copy of the production Dockerfile.
# Does NOT affect your stash-git image or any running containers.
#
# Added on top of production:
#   - gcompat: lets Alpine run manylinux (glibc) wheels, needed for torch
#   - ultralytics + opencv-python-headless: ML inference for the classifier
#   - `python` symlink: Alpine only provides `python3`; the plugin manifest needs `python`
#
# Build via Makefile: make start-dev

FROM stashapp/stash:v0.31.1

RUN apk add --no-cache \
    ca-certificates \
    python3 \
    py3-pip \
    py3-requests \
    py3-requests-toolbelt \
    py3-lxml \
    ffmpeg \
    ruby \
    tzdata \
    vips \
    vips-tools \
    git \
    gcompat

RUN set -x && pip install --break-system-packages \
    mechanicalsoup \
    cloudscraper \
    stashapp-tools \
    google-api-python-client \
    Pillow && \
    gem install faraday

# ML dependencies for the stash-image-classifier plugin
RUN pip install --break-system-packages \
    ultralytics \
    opencv-python-headless \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Alpine's python3 package doesn't create a bare `python` symlink
RUN ln -sf /usr/bin/python3 /usr/bin/python
