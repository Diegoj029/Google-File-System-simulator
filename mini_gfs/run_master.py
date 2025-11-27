#!/usr/bin/env python3
"""
Script para ejecutar el Master del mini-GFS.
"""
import sys
import signal
import threading
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from mini_gfs.master.master import Master
from mini_gfs.master.api import run_master_server

# Variable global para el servidor y master
_server = None
_master = None
_shutdown_event = threading.Event()


def signal_handler(sig, frame):
    """Maneja señales para detener el servidor limpiamente."""
    print("\nRecibida señal de interrupción, deteniendo Master...")
    _shutdown_event.set()
    if _server:
        # shutdown() debe llamarse desde otro thread
        def shutdown_server():
            try:
                _server.shutdown()
            except:
                pass
        thread = threading.Thread(target=shutdown_server, daemon=True)
        thread.start()


def main():
    """Función principal."""
    global _server, _master
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Crear e iniciar Master
    _master = Master()
    _master.start()
    
    server_thread = None
    try:
        # Crear servidor HTTP
        _server = run_master_server(_master, _master.config.host, _master.config.port)
        # Iniciar el servidor (bloqueante)
        # Usar un thread para servir y poder detectar el evento de shutdown
        server_thread = threading.Thread(target=_server.serve_forever, daemon=False)
        server_thread.start()
        
        # Esperar hasta que se reciba la señal de shutdown
        _shutdown_event.wait()
        
    except KeyboardInterrupt:
        print("\nDeteniendo Master API server...")
    finally:
        if _server:
            try:
                # Cerrar el servidor
                _server.shutdown()
                # Esperar a que el thread del servidor termine
                if server_thread and server_thread.is_alive():
                    server_thread.join(timeout=2)
                # Cerrar el socket
                _server.server_close()
            except Exception as e:
                # Si hay un error, intentar cerrar el socket directamente
                try:
                    if hasattr(_server, 'socket') and _server.socket:
                        _server.socket.close()
                except:
                    pass
        if _master:
            _master.stop()


if __name__ == '__main__':
    main()

