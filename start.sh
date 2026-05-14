#!/bin/bash
# APT Mining Workbench - Start (Linux/macOS)
set -e

cd "$(dirname "$0")"

python3 start.py "$@"
