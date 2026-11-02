#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  python3 scripts/setup.py
fi
.venv/bin/python scripts/setup.py
exec .venv/bin/python -m liquidframe "$@"
