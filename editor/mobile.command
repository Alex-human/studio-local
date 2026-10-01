#!/bin/zsh
set -euo pipefail
exec "${0:A:h}/.venv/bin/python3" "${0:A:h}/mobile/server.py" "$@"
