FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHON_VERSION=3.12.4
ENV VIDEO_EVENT_LOGGER_CONTAINER_BUILD=1

WORKDIR /app

RUN test "$(uname -m)" = "x86_64" \
    && test "$(dpkg --print-architecture)" = "amd64"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils \
        build-essential \
        ca-certificates \
        curl \
        file \
        libbz2-dev \
        libffi-dev \
        libgdbm-dev \
        libgtk-3-0 \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        libxcb-cursor0 \
        patchelf \
        tk-dev \
        uuid-dev \
        vlc \
        wget \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" \
    && tar -xzf "Python-${PYTHON_VERSION}.tgz" \
    && cd "Python-${PYTHON_VERSION}" \
    && ./configure --enable-shared --enable-optimizations --with-ensurepip=install \
    && make -j"$(nproc)" \
    && make altinstall \
    && cd /app \
    && echo "/usr/local/lib" > /etc/ld.so.conf.d/python3.12.conf \
    && ldconfig \
    && rm -rf "Python-${PYTHON_VERSION}" "Python-${PYTHON_VERSION}.tgz" \
    && python3.12 --version \
    && ldd "$(command -v python3.12)" \
    && ! ldd "$(command -v python3.12)" | grep -F "not found" \
    && ldconfig -p | grep -F "libpython3.12"

COPY . /app

RUN chmod +x packaging/ubuntu_20_04/*.sh

CMD ["bash", "packaging/ubuntu_20_04/build_in_container.sh"]
