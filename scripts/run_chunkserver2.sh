#!/bin/bash
# Script para ejecutar el segundo ChunkServer

cd "$(dirname "$0")/.." || exit 1

python3 mini_gfs/run_chunkserver.py --port 8002 --id cs2 --data-dir data/chunks/cs2

