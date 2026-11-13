#!/usr/bin/env bash
set -euo pipefail

# Run only in the disposable runtime_test.Dockerfile container.
grep -q '^VERSION_ID="24.04"$' /etc/os-release
if ldconfig -p | grep -E 'lib(ssl|crypto)\.so\.1\.1'; then
  echo "Runtime test requires an environment without OpenSSL 1.1." >&2
  exit 1
fi
test ! -d /opt/video-event-logger-openssl
mkdir -p /tmp/release-under-test
tar -xzf /input/release.tar.gz -C /tmp/release-under-test
installer="$(find /tmp/release-under-test -mindepth 2 -maxdepth 2 -name install.sh -print -quit)"
test -n "$installer"
timeout 120 bash "$installer"
timeout 60 /root/.local/opt/video-event-logger/video-event-logger-launcher --smoke-test
echo "Installation and installed launcher passed on Ubuntu 24.04 without OpenSSL 1.1."
