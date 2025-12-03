#!/usr/bin/env python3
"""
Script para ejecutar la interfaz web del mini-GFS.

Inicia el servidor web que permite gestionar el sistema GFS
desde una interfaz gráfica en el navegador.
"""
import sys
import signal
import threading
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from mini_gfs.web.process_manager import ProcessManager
from mini_gfs.web.metrics_collector import MetricsCollector
from mini_gfs.web.visualization import VisualizationGenerator
from mini_gfs.web.server import run_web_server

# Variables globales
_server = None
_process_manager = None
_metrics_collector = None
_shutdown_event = threading.Event()


def signal_handler(sig, frame):
    """Maneja señales para detener el servidor limpiamente."""
    print("\n\nRecibida señal de interrupción, deteniendo servidor web...")
    _shutdown_event.set()
    
    # Detener servidor web
    if _server:
        def shutdown_server():
            try:
                _server.shutdown()
            except:
                pass
        thread = threading.Thread(target=shutdown_server, daemon=True)
        thread.start()
    
    # Detener todos los procesos del sistema
    if _process_manager:
        print("Deteniendo procesos del sistema GFS...")
        _process_manager.stop_all()
        # También matar procesos huérfanos
        _process_manager.kill_all_processes()


def main():
    """Función principal."""
    global _server, _process_manager, _metrics_collector
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 60)
    print("Mini-GFS - Interfaz Web")
    print("=" * 60)
    print()
    
    # Inicializar componentes
    print("Inicializando componentes...")
    _process_manager = ProcessManager(master_port=8000, chunkserver_ports=[8001, 8002, 8003])
    _metrics_collector = MetricsCollector(master_address="http://localhost:8000")
    visualization = VisualizationGenerator(output_dir="output")
    
    print("Componentes inicializados correctamente")
    print()
    
    # Iniciar servidor web
    try:
        _server = run_web_server(
            _process_manager,
            _metrics_collector,
            visualization,
            host="localhost",
            port=8080
        )
        
        print()
        print("=" * 60)
        print("✅ Interfaz web disponible en:")
        print(f"   http://localhost:8080")
        print()
        print("Presiona Ctrl+C para detener el servidor")
        print("=" * 60)
        print()
        
        # Iniciar thread para recolectar métricas periódicamente
        def metrics_worker():
            while not _shutdown_event.is_set():
                try:
                    _metrics_collector.collect()
                except Exception as e:
                    # Solo imprimir errores inesperados (no errores de conexión)
                    import requests
                    if not isinstance(e, (requests.exceptions.ConnectionError,
                                        requests.exceptions.Timeout,
                                        requests.exceptions.RequestException)):
                        print(f"Error inesperado recolectando métricas: {e}")
                _shutdown_event.wait(5)  # Esperar 5 segundos o hasta shutdown
        
        metrics_thread = threading.Thread(target=metrics_worker, daemon=True)
        metrics_thread.start()
        
        # Iniciar servidor en thread separado
        server_thread = threading.Thread(target=_server.serve_forever, daemon=False)
        server_thread.start()
        
        # Esperar hasta que se reciba la señal de shutdown
        _shutdown_event.wait()
        
    except KeyboardInterrupt:
        print("\nDeteniendo servidor web...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Limpiar - asegurar que todo se detenga
        print("\nLimpiando recursos...")
        
        # Detener servidor web
        if _server:
            try:
                print("Deteniendo servidor web...")
                _server.shutdown()
                if 'server_thread' in locals() and server_thread.is_alive():
                    server_thread.join(timeout=3)
                _server.server_close()
            except Exception as e:
                print(f"Error deteniendo servidor web: {e}")
        
        # Detener todos los procesos del sistema
        if _process_manager:
            print("Deteniendo procesos del sistema GFS...")
            try:
                _process_manager.stop_all()
                # Matar procesos huérfanos si es necesario
                _process_manager.kill_all_processes()
            except Exception as e:
                print(f"Error deteniendo procesos: {e}")
        
        print("✅ Servidor web detenido correctamente")


if __name__ == '__main__':
    main()

