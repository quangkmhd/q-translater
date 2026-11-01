#!/bin/sh
set -eu
QT_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$QT_PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m qtranslate "$@"
