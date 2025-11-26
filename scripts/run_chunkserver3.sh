#!/bin/bash
# Script para ejecutar el tercer ChunkServer

cd "$(dirname "$0")/.." || exit 1

python3 mini_gfs/run_chunkserver.py --port 8003 --id cs3 --data-dir data/chunks/cs3

