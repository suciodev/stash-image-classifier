# Dev image for local plugin testing. Safe copy of the production Dockerfile.
# Does NOT affect your stash-git image or any running containers.
#
# Added on top of production:
#   - gcompat:    lets Alpine run manylinux (glibc) wheels, needed for torch
#   - py3-opencv: OpenCV from Alpine apk (avoids compiling from source)
#   - ultralytics: ML inference for the classifier
#   - `python` symlink: Alpine only provides `python3`; the plugin manifest needs `python`
#   - libgomp_stub.so + LD_PRELOAD: stubs pthread_attr_setaffinity_np missing from musl
#
# Why py3-opencv via apk instead of pip?
#   opencv-python(-headless) has no pre-built Alpine/musl wheels on PyPI. pip
#   falls back to compiling from source, which needs cmake/ninja/gcc — not in
#   the image. The apk package provides the same cv2 module, pre-compiled.
#   Fake dist-infos are registered so pip resolves ultralytics' opencv dependency
#   without downloading or building anything.
#
# Why the LD_PRELOAD stub?
#   torch's bundled libgomp-*.so.1 was compiled against glibc and calls
#   pthread_attr_setaffinity_np (a GNU extension for CPU affinity). musl doesn't
#   provide it and gcompat doesn't stub it, so dlopen fails at import time. The
#   stub is a no-op that satisfies the relocation so torch loads normally.
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
    gcompat \
    py3-opencv

RUN set -x && pip install --break-system-packages \
    mechanicalsoup \
    cloudscraper \
    stashapp-tools \
    google-api-python-client \
    Pillow && \
    gem install faraday

# Register fake dist-infos for opencv-python and opencv-python-headless so pip
# treats both as already satisfied when resolving ultralytics' dependencies.
RUN SITE=$(python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))") && \
    VER=$(python3 -c "import cv2; print(cv2.__version__)") && \
    mkdir -p "$SITE/opencv_python-${VER}.dist-info" && \
    printf "Metadata-Version: 2.1\nName: opencv-python\nVersion: %s\n" "$VER" \
        > "$SITE/opencv_python-${VER}.dist-info/METADATA" && \
    touch "$SITE/opencv_python-${VER}.dist-info/RECORD" && \
    mkdir -p "$SITE/opencv_python_headless-${VER}.dist-info" && \
    printf "Metadata-Version: 2.1\nName: opencv-python-headless\nVersion: %s\n" "$VER" \
        > "$SITE/opencv_python_headless-${VER}.dist-info/METADATA" && \
    touch "$SITE/opencv_python_headless-${VER}.dist-info/RECORD"

# torch manylinux wheels run on Alpine via gcompat; ultralytics picks them up.
RUN pip install --break-system-packages \
    ultralytics \
    --extra-index-url https://download.pytorch.org/whl/cpu

# torch's bundled libgomp was compiled against glibc and references
# pthread_attr_setaffinity_np, a GNU extension absent from musl/gcompat.
# Compile a no-op stub and preload it so dlopen resolves the symbol.
RUN apk add --no-cache --virtual .stub-build gcc musl-dev && \
    printf 'int pthread_attr_setaffinity_np(void *a,unsigned long b,void *c){return 0;}\n' \
        > /tmp/stub.c && \
    gcc -shared -fPIC -o /usr/local/lib/libgomp_stub.so /tmp/stub.c && \
    rm /tmp/stub.c && \
    apk del .stub-build
ENV LD_PRELOAD=/usr/local/lib/libgomp_stub.so

# Alpine's python3 package doesn't create a bare `python` symlink
RUN ln -sf /usr/bin/python3 /usr/bin/python
