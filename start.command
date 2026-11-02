#!/bin/zsh
set -e
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  for interpreter in python3.13 python3.12 python3.11 python3; do
    if command -v "$interpreter" >/dev/null && "$interpreter" -c 'import sys; sys.exit(sys.version_info < (3,11))'; then
      "$interpreter" scripts/setup.py
      break
    fi
  done
fi
if [[ ! -x .venv/bin/python ]]; then
  print 'Install Python 3.11+ from python.org, then try again.'
  read 'reply?Press Return to close.'
  exit 1
fi
.venv/bin/python scripts/setup.py
exec .venv/bin/python -m liquidframe "$@"
