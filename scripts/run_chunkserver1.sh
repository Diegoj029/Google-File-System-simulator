#!/bin/bash
# Script para ejecutar el primer ChunkServer

cd "$(dirname "$0")/.." || exit 1

python3 mini_gfs/run_chunkserver.py --port 8001 --id cs1 --data-dir data/chunks/cs1

