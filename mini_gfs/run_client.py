#!/usr/bin/env python3
"""
Script para ejecutar el Cliente CLI del mini-GFS.
"""
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from mini_gfs.client.cli import main

if __name__ == '__main__':
    main()

