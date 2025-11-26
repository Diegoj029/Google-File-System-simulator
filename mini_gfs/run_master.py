#!/usr/bin/env python3
"""
Script para ejecutar el Master del mini-GFS.
"""
import sys
import signal
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from mini_gfs.master.master import Master
from mini_gfs.master.api import run_master_server


def signal_handler(sig, frame):
    """Maneja señales para detener el servidor limpiamente."""
    print("\nRecibida señal de interrupción, deteniendo Master...")
    sys.exit(0)


def main():
    """Función principal."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Crear e iniciar Master
    master = Master()
    master.start()
    
    try:
        # Iniciar servidor HTTP
        run_master_server(master, master.config.host, master.config.port)
    except KeyboardInterrupt:
        pass
    finally:
        master.stop()


if __name__ == '__main__':
    main()

