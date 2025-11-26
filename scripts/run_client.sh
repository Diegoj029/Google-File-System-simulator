#!/bin/bash
# Script para ejecutar el Cliente CLI

cd "$(dirname "$0")/.." || exit 1

python3 mini_gfs/run_client.py "$@"

