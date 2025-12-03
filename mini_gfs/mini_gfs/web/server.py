"""
Servidor web para la interfaz gráfica del mini-GFS.

Sirve archivos estáticos y expone una API REST para interactuar
con el sistema GFS.
"""
import json
import os
import socket
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Optional
import requests

from .process_manager import ProcessManager
from .metrics_collector import MetricsCollector
from .visualization import VisualizationGenerator


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    """ThreadingTCPServer con SO_REUSEADDR habilitado."""
    allow_reuse_address = True
    
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class WebAPIHandler(BaseHTTPRequestHandler):
    """Handler HTTP para la API web y archivos estáticos."""
    
    def __init__(self, process_manager: ProcessManager, metrics_collector: MetricsCollector,
                 visualization: VisualizationGenerator, static_dir: Path, *args, **kwargs):
        self.process_manager = process_manager
        self.metrics_collector = metrics_collector
        self.visualization = visualization
        self.static_dir = static_dir
        self.master_address = process_manager.master_address
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Maneja peticiones GET."""
        path = urlparse(self.path).path
        
        # API endpoints
        if path.startswith('/api/'):
            self._handle_api_get(path)
        else:
            # Archivos estáticos
            self._handle_static_file(path)
    
    def do_POST(self):
        """Maneja peticiones POST."""
        path = urlparse(self.path).path
        
        if not path.startswith('/api/'):
            self._send_error(404, "Not found")
            return
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            data = {}
        
        self._handle_api_post(path, data)
    
    def _handle_api_get(self, path: str):
        """Maneja peticiones GET de la API."""
        query_params = parse_qs(urlparse(self.path).query)
        
        if path == '/api/system/status':
            response = self._get_system_status()
        elif path == '/api/system/topology':
            response = self._get_topology()
        elif path == '/api/files/list':
            response = self._list_files()
        elif path == '/api/files/info':
            file_path = query_params.get('path', [None])[0]
            response = self._get_file_info(file_path)
        elif path == '/api/chunks/distribution':
            file_path = query_params.get('file_path', [None])[0]
            response = self._get_chunk_distribution(file_path)
        elif path == '/api/config/get':
            response = self._get_config()
        elif path == '/api/metrics/current':
            response = self._get_current_metrics()
        elif path == '/api/metrics/history':
            limit = int(query_params.get('limit', [100])[0])
            response = self._get_metrics_history(limit)
        elif path == '/api/metrics/graph':
            response = self._generate_performance_graph()
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def _handle_api_post(self, path: str, data: dict):
        """Maneja peticiones POST de la API."""
        if path == '/api/system/start':
            response = self._start_system()
        elif path == '/api/system/stop':
            response = self._stop_system()
        elif path == '/api/files/create':
            response = self._create_file(data)
        elif path == '/api/files/write':
            response = self._write_file(data)
        elif path == '/api/files/read':
            response = self._read_file(data)
        elif path == '/api/files/delete':
            response = self._delete_file(data)
        elif path == '/api/config/update':
            response = self._update_config(data)
        elif path == '/api/metrics/graph':
            response = self._generate_performance_graph()
        elif path == '/api/visualization/topology':
            response = self._generate_topology_image()
        elif path == '/api/visualization/distribution':
            file_path = data.get('file_path')
            response = self._generate_distribution_image(file_path)
        elif path == '/api/visualization/cluster':
            response = self._generate_cluster_view()
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def _get_system_status(self) -> dict:
        """Obtiene el estado del sistema."""
        process_status = self.process_manager.get_status()
        
        # Verificar estado del Master
        master_status = "running" if process_status["master"]["running"] else "stopped"
        
        chunkservers_status = {}
        for cs_id, cs_info in process_status["chunkservers"].items():
            chunkservers_status[cs_id] = {
                "running": cs_info["running"],
                "pid": cs_info["pid"]
            }
        
        return {
            "success": True,
            "master": {
                "status": master_status,
                "pid": process_status["master"]["pid"]
            },
            "chunkservers": chunkservers_status
        }
    
    def _get_topology(self) -> dict:
        """Obtiene la topología de red."""
        try:
            response = requests.get(f"{self.master_address}/topology", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": "Error obteniendo topología"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _list_files(self) -> dict:
        """Lista archivos en el sistema."""
        try:
            response = requests.post(
                f"{self.master_address}/list_directory",
                json={"dir_path": "/"},
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "files": result.get("files", [])
                }
            else:
                return {"success": False, "message": "Error listando archivos"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _get_file_info(self, file_path: Optional[str]) -> dict:
        """Obtiene información de un archivo."""
        if not file_path:
            return {"success": False, "message": "Missing file path"}
        
        try:
            response = requests.post(
                f"{self.master_address}/get_file_info",
                json={"path": file_path},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": "Error obteniendo información del archivo"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _get_chunk_distribution(self, file_path: Optional[str]) -> dict:
        """Obtiene la distribución de chunks."""
        try:
            url = f"{self.master_address}/chunks/distribution"
            if file_path:
                url += f"?file_path={file_path}"
            
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": "Error obteniendo distribución de chunks"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _get_config(self) -> dict:
        """Obtiene la configuración actual."""
        try:
            response = requests.get(f"{self.master_address}/system_state", timeout=5)
            if response.status_code == 200:
                state = response.json()
                return {
                    "success": True,
                    "replication_factor": state.get("replication_factor", 3),
                    "chunk_size": state.get("chunk_size", 1048576),
                    "heartbeat_timeout": 30,  # TODO: obtener del config real
                    "lease_duration": 60  # TODO: obtener del config real
                }
            else:
                return {"success": False, "message": "Error obteniendo configuración"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _get_current_metrics(self) -> dict:
        """Obtiene métricas actuales."""
        # Recolectar métricas primero
        self.metrics_collector.collect()
        metrics = self.metrics_collector.get_current()
        
        if metrics:
            return {"success": True, "metrics": metrics}
        else:
            return {"success": False, "message": "No hay métricas disponibles"}
    
    def _get_metrics_history(self, limit: int) -> dict:
        """Obtiene historial de métricas."""
        history = self.metrics_collector.get_history(limit)
        return {"success": True, "history": history}
    
    def _start_system(self) -> dict:
        """Inicia el sistema."""
        try:
            success = self.process_manager.start_all()
            if success:
                return {
                    "success": True,
                    "message": "Sistema iniciado correctamente (Master + 3 ChunkServers)"
                }
            else:
                return {
                    "success": False,
                    "message": "Error: Algunos componentes no se iniciaron. Revisa los logs en la consola."
                }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error iniciando sistema: {e}")
            print(error_details)
            return {
                "success": False,
                "message": f"Error iniciando sistema: {str(e)}"
            }
    
    def _stop_system(self) -> dict:
        """Detiene el sistema."""
        self.process_manager.stop_all()
        return {"success": True, "message": "Sistema detenido"}
    
    def _create_file(self, data: dict) -> dict:
        """Crea un archivo."""
        path = data.get('path')
        if not path:
            return {"success": False, "message": "Missing path"}
        
        try:
            response = requests.post(
                f"{self.master_address}/create_file",
                json={"path": path},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": "Error creando archivo"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _write_file(self, data: dict) -> dict:
        """Escribe en un archivo."""
        # Esta operación requiere usar el cliente API
        # Por ahora, retornamos un mensaje indicando que se debe usar el cliente
        return {
            "success": False,
            "message": "Use el cliente API para escribir archivos"
        }
    
    def _read_file(self, data: dict) -> dict:
        """Lee un archivo."""
        # Similar a write_file, requiere cliente API
        return {
            "success": False,
            "message": "Use el cliente API para leer archivos"
        }
    
    def _delete_file(self, data: dict) -> dict:
        """Elimina un archivo."""
        path = data.get('path')
        if not path:
            return {"success": False, "message": "Missing path"}
        
        try:
            response = requests.post(
                f"{self.master_address}/delete_file",
                json={"path": path},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": "Error eliminando archivo"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _update_config(self, data: dict) -> dict:
        """Actualiza la configuración."""
        # Por ahora, solo retornamos un mensaje
        # La actualización real de configuración requeriría modificar el archivo YAML
        return {
            "success": False,
            "message": "Actualización de configuración no implementada aún"
        }
    
    def _generate_performance_graph(self) -> dict:
        """Genera gráfica de rendimiento."""
        history = self.metrics_collector.get_history(100)
        if not history:
            return {"success": False, "message": "No hay métricas disponibles"}
        
        file_path = self.visualization.generate_performance_graph(history)
        if file_path:
            return {
                "success": True,
                "file_path": file_path,
                "url": f"/output/{Path(file_path).name}"
            }
        else:
            return {"success": False, "message": "Error generando gráfica"}
    
    def _generate_topology_image(self) -> dict:
        """Genera imagen de topología."""
        topology = self._get_topology()
        if not topology.get("success"):
            return topology
        
        file_path = self.visualization.generate_network_topology(topology)
        if file_path:
            return {
                "success": True,
                "file_path": file_path,
                "url": f"/output/{Path(file_path).name}"
            }
        else:
            return {"success": False, "message": "Error generando topología"}
    
    def _generate_distribution_image(self, file_path: Optional[str]) -> dict:
        """Genera imagen de distribución de chunks."""
        distribution = self._get_chunk_distribution(file_path)
        if not distribution.get("success"):
            return distribution
        
        img_file_path = self.visualization.generate_chunk_distribution(distribution, file_path)
        if img_file_path:
            return {
                "success": True,
                "file_path": img_file_path,
                "url": f"/output/{Path(img_file_path).name}"
            }
        else:
            return {"success": False, "message": "Error generando distribución"}
    
    def _generate_cluster_view(self) -> dict:
        """Genera vista del cluster."""
        try:
            response = requests.get(f"{self.master_address}/system_state", timeout=5)
            if response.status_code != 200:
                return {"success": False, "message": "Error obteniendo estado del sistema"}
            
            master_state = response.json()
            file_path = self.visualization.generate_cluster_view(master_state)
            
            if file_path:
                return {
                    "success": True,
                    "file_path": file_path,
                    "url": f"/output/{Path(file_path).name}"
                }
            else:
                return {"success": False, "message": "Error generando vista del cluster"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _handle_static_file(self, path: str):
        """Sirve archivos estáticos."""
        if path == '/' or path == '':
            path = '/index.html'
        
        # Mapear /output/ al directorio output
        if path.startswith('/output/'):
            # Obtener ruta base del proyecto
            base_path = Path(__file__).parent.parent.parent.parent
            file_path = base_path / 'output' / path[8:]
        else:
            file_path = self.static_dir / path.lstrip('/')
        
        if not file_path.exists() or not file_path.is_file():
            self._send_error(404, "File not found")
            return
        
        # Determinar content type
        content_type = 'text/html'
        if path.endswith('.css'):
            content_type = 'text/css'
        elif path.endswith('.js'):
            content_type = 'application/javascript'
        elif path.endswith('.png'):
            content_type = 'image/png'
        elif path.endswith('.jpg') or path.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif path.endswith('.json'):
            content_type = 'application/json'
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(500, str(e))
    
    def _send_json_response(self, data: dict):
        """Envía una respuesta JSON."""
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')  # CORS
        self.end_headers()
        self.wfile.write(response)
    
    def _send_error(self, code: int, message: str):
        """Envía un error HTTP."""
        response = json.dumps({"success": False, "message": message}).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    
    def log_message(self, format, *args):
        """Override para logging personalizado."""
        print(f"[Web Server] {format % args}")


def create_web_handler(process_manager: ProcessManager, metrics_collector: MetricsCollector,
                       visualization: VisualizationGenerator, static_dir: Path):
    """Factory function para crear handlers con referencias."""
    def handler(*args, **kwargs):
        return WebAPIHandler(process_manager, metrics_collector, visualization, static_dir, *args, **kwargs)
    return handler


def run_web_server(process_manager: ProcessManager, metrics_collector: MetricsCollector,
                  visualization: VisualizationGenerator, host: str = "localhost", port: int = 8080):
    """
    Inicia el servidor web.
    
    Args:
        process_manager: Gestor de procesos
        metrics_collector: Recolector de métricas
        visualization: Generador de visualizaciones
        host: Dirección del servidor
        port: Puerto del servidor
    
    Returns:
        El servidor creado
    """
    static_dir = Path(__file__).parent / "static"
    handler = create_web_handler(process_manager, metrics_collector, visualization, static_dir)
    server = ReusableThreadingTCPServer((host, port), handler)
    
    print(f"Servidor web iniciado en http://{host}:{port}")
    
    return server

