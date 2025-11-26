#!/usr/bin/env python3
"""
Script para ejecutar un ChunkServer del mini-GFS.
"""
import sys
import signal
import argparse
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from mini_gfs.chunkserver.chunkserver import ChunkServer
from mini_gfs.chunkserver.api import run_chunkserver_server
from mini_gfs.common.config import ChunkServerConfig, load_chunkserver_config, load_master_config


def signal_handler(sig, frame):
    """Maneja señales para detener el servidor limpiamente."""
    print("\nRecibida señal de interrupción, deteniendo ChunkServer...")
    sys.exit(0)


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(description='Ejecuta un ChunkServer del mini-GFS')
    parser.add_argument('--port', type=int, help='Puerto del ChunkServer')
    parser.add_argument('--id', type=str, help='ID del ChunkServer')
    parser.add_argument('--data-dir', type=str, help='Directorio de datos')
    parser.add_argument('--master', type=str, help='Dirección del Master')
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Cargar configuración
    config = load_chunkserver_config()
    
    # Sobrescribir con argumentos de línea de comandos si se proporcionan
    if args.port:
        config.port = args.port
    if args.id:
        config.chunkserver_id = args.id
    if args.data_dir:
        config.data_dir = args.data_dir
    if args.master:
        config.master_address = args.master
    
    # Crear e iniciar ChunkServer
    chunkserver = ChunkServer(config)
    chunkserver.start()
    
    # Obtener chunk_size del Master config
    master_config = load_master_config()
    chunk_size = master_config.chunk_size
    
    try:
        # Iniciar servidor HTTP
        run_chunkserver_server(chunkserver, chunk_size, config.host, config.port)
    except KeyboardInterrupt:
        pass
    finally:
        chunkserver.stop()


if __name__ == '__main__':
    main()

