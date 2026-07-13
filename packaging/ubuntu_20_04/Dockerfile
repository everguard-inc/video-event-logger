FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHON_VERSION=3.12.4
ENV LD_LIBRARY_PATH=/usr/local/lib

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libbz2-dev \
        libffi-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        tk-dev \
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
    && python3.12 --version

COPY . /app

RUN chmod +x packaging/ubuntu_20_04/*.sh

CMD ["bash", "-lc", "PYTHON_BIN=python3.12 VENV_DIR=/tmp/video-event-logger-packaging-venv bash packaging/ubuntu_20_04/build.sh && bash packaging/ubuntu_20_04/create_release_archive.sh"]
