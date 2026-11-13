# A consumer environment, separate from the compiler/build image.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates file vlc vlc-plugin-base libxcb-cursor0 libgtk-3-0t64 \
    && rm -rf /var/lib/apt/lists/*
COPY packaging/ubuntu_20_04/test_installed_release.sh /test_installed_release.sh
CMD ["bash", "/test_installed_release.sh"]
