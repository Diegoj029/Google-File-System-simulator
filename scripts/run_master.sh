#!/bin/bash
# Script para ejecutar el Master

cd "$(dirname "$0")/.." || exit 1

python3 mini_gfs/run_master.py

