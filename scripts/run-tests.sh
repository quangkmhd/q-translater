#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH=src
/usr/bin/python3 -m unittest discover -s tests -v
if [ -d extension/qtranslate@local/tests ]; then
  node --test extension/qtranslate@local/tests/*.test.js
fi
