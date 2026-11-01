#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec env PYTHONPATH=src /usr/bin/python3 packaging/build_deb.py "$@"
