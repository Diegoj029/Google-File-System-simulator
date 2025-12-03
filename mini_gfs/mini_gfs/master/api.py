"""
API HTTP del Master.

Expone endpoints JSON para que ChunkServers y Clients
se comuniquen con el Master.
"""
import json
import base64
import socket
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

from .master import Master
from ..common.types import ChunkHandle


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    """ThreadingTCPServer con SO_REUSEADDR habilitado para reutilizar puertos."""
    allow_reuse_address = True
    
    def server_bind(self):
        """Configura el socket con SO_REUSEADDR antes de hacer bind."""
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class MasterAPIHandler(BaseHTTPRequestHandler):
    """
    Handler HTTP para las peticiones al Master.
    
    Maneja todas las operaciones del Master vía JSON sobre HTTP.
    """
    
    def __init__(self, master: Master, *args, **kwargs):
        self.master = master
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Maneja todas las peticiones GET."""
        path = urlparse(self.path).path
        query_params = parse_qs(urlparse(self.path).query)
        
        # Enrutar según el path
        if path == '/system_state':
            response = self._handle_get_system_state()
        elif path == '/metrics':
            response = self._handle_get_metrics()
        elif path == '/topology':
            response = self._handle_get_topology()
        elif path == '/chunks/distribution':
            file_path = query_params.get('file_path', [None])[0]
            response = self._handle_get_chunk_distribution(file_path)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def do_POST(self):
        """Maneja todas las peticiones POST."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return
        
        path = urlparse(self.path).path
        
        # Enrutar según el path
        if path == '/register_chunkserver':
            response = self._handle_register_chunkserver(data)
        elif path == '/heartbeat':
            response = self._handle_heartbeat(data)
        elif path == '/create_file':
            response = self._handle_create_file(data)
        elif path == '/get_file_info':
            response = self._handle_get_file_info(data)
        elif path == '/allocate_chunk':
            response = self._handle_allocate_chunk(data)
        elif path == '/get_chunk_locations':
            response = self._handle_get_chunk_locations(data)
        elif path == '/snapshot_file':
            response = self._handle_snapshot_file(data)
        elif path == '/clone_shared_chunk':
            response = self._handle_clone_shared_chunk(data)
        elif path == '/rename_file':
            response = self._handle_rename_file(data)
        elif path == '/delete_file':
            response = self._handle_delete_file(data)
        elif path == '/list_directory':
            response = self._handle_list_directory(data)
        elif path == '/update_chunk_size':
            response = self._handle_update_chunk_size(data)
        elif path == '/record_operation':
            response = self._handle_record_operation(data)
        elif path == '/clone_shared_chunk':
            response = self._handle_clone_shared_chunk(data)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def _handle_register_chunkserver(self, data: dict) -> dict:
        """Maneja registro de ChunkServer."""
        chunkserver_id = data.get('chunkserver_id')
        address = data.get('address')
        chunks = data.get('chunks', [])
        rack_id = data.get('rack_id', 'default')
        
        if not chunkserver_id or not address:
            return {"success": False, "message": "Missing chunkserver_id or address"}
        
        success = self.master.register_chunkserver(chunkserver_id, address, chunks, rack_id)
        return {
            "success": success,
            "message": "Registered successfully" if success else "Registration failed"
        }
    
    def _handle_heartbeat(self, data: dict) -> dict:
        """Maneja heartbeat de ChunkServer."""
        chunkserver_id = data.get('chunkserver_id')
        chunks = data.get('chunks', [])
        
        if not chunkserver_id:
            return {"success": False, "message": "Missing chunkserver_id"}
        
        success = self.master.handle_heartbeat(chunkserver_id, chunks)
        return {
            "success": success,
            "message": "Heartbeat received" if success else "Heartbeat failed"
        }
    
    def _handle_create_file(self, data: dict) -> dict:
        """Maneja creación de archivo."""
        path = data.get('path')
        
        if not path:
            return {"success": False, "message": "Missing path"}
        
        success = self.master.create_file(path)
        return {
            "success": success,
            "message": "File created" if success else "File already exists or creation failed"
        }
    
    def _handle_get_file_info(self, data: dict) -> dict:
        """Maneja obtención de información de archivo."""
        path = data.get('path')
        
        if not path:
            return {"success": False, "message": "Missing path"}
        
        file_info = self.master.get_file_info(path)
        if not file_info:
            return {"success": False, "message": "File not found"}
        
        return {
            "success": True,
            "path": file_info["path"],
            "chunk_handles": file_info["chunk_handles"],
            "chunks_info": file_info["chunks_info"]
        }
    
    def _handle_allocate_chunk(self, data: dict) -> dict:
        """Maneja asignación de chunk."""
        try:
            path = data.get('path')
            chunk_index = data.get('chunk_index')
            
            if path is None or chunk_index is None:
                return {"success": False, "message": "Missing path or chunk_index"}
            
            print(f"[Master] Asignando chunk para {path}, índice {chunk_index}")
            chunk_handle, replicas, primary_id = self.master.allocate_chunk(path, chunk_index)
            
            if not chunk_handle:
                print(f"[Master] Error: No se pudo asignar chunk (posiblemente no hay chunkservers disponibles)")
                return {"success": False, "message": "Failed to allocate chunk - no available chunkservers"}
            
            print(f"[Master] Chunk asignado: {chunk_handle}, réplicas: {len(replicas)}")
            return {
                "success": True,
                "chunk_handle": chunk_handle,
                "replicas": [
                    {
                        "chunkserver_id": r.chunkserver_id,
                        "address": r.address
                    }
                    for r in replicas
                ],
                "primary_id": primary_id
            }
        except Exception as e:
            print(f"[Master] Excepción en allocate_chunk: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"Exception: {str(e)}"}
    
    def _handle_get_chunk_locations(self, data: dict) -> dict:
        """Maneja obtención de ubicaciones de chunk."""
        chunk_handle = data.get('chunk_handle')
        
        if not chunk_handle:
            return {"success": False, "message": "Missing chunk_handle"}
        
        locations = self.master.get_chunk_locations(chunk_handle)
        if not locations:
            return {"success": False, "message": "Chunk not found"}
        
        return {
            "success": True,
            "chunk_handle": locations["chunk_handle"],
            "replicas": locations["replicas"],
            "primary_id": locations["primary_id"],
            "size": locations.get("size", 0),
            "reference_count": locations.get("reference_count", 1)
        }
    
    def _handle_clone_shared_chunk(self, data: dict) -> dict:
        """Maneja clonación de chunk compartido para copy-on-write."""
        path = data.get('path')
        chunk_index = data.get('chunk_index')
        old_chunk_handle = data.get('old_chunk_handle')
        
        if not path or chunk_index is None or not old_chunk_handle:
            return {"success": False, "message": "Missing path, chunk_index, or old_chunk_handle"}
        
        new_chunk_handle = self.master.clone_shared_chunk(path, chunk_index, old_chunk_handle)
        
        if not new_chunk_handle:
            return {"success": False, "message": "Failed to clone shared chunk"}
        
        return {
            "success": True,
            "chunk_handle": new_chunk_handle,
            "message": "Chunk cloned successfully"
        }
    
    def _handle_snapshot_file(self, data: dict) -> dict:
        """Maneja creación de snapshot de archivo."""
        source_path = data.get('source_path')
        dest_path = data.get('dest_path')
        
        if not source_path or not dest_path:
            return {"success": False, "message": "Missing source_path or dest_path"}
        
        success = self.master.snapshot_file(source_path, dest_path)
        return {
            "success": success,
            "message": "Snapshot created" if success else "Snapshot failed"
        }
    
    def _handle_rename_file(self, data: dict) -> dict:
        """Maneja renombrado de archivo."""
        old_path = data.get('old_path')
        new_path = data.get('new_path')
        
        if not old_path or not new_path:
            return {"success": False, "message": "Missing old_path or new_path"}
        
        success = self.master.rename_file(old_path, new_path)
        return {
            "success": success,
            "message": "File renamed" if success else "Rename failed"
        }
    
    def _handle_delete_file(self, data: dict) -> dict:
        """Maneja eliminación de archivo."""
        path = data.get('path')
        
        if not path:
            return {"success": False, "message": "Missing path"}
        
        success = self.master.delete_file(path)
        return {
            "success": success,
            "message": "File deleted" if success else "Delete failed"
        }
    
    def _handle_list_directory(self, data: dict) -> dict:
        """Maneja listado de directorio."""
        dir_path = data.get('dir_path', '/')
        
        files = self.master.list_directory(dir_path)
        return {
            "success": True,
            "dir_path": dir_path,
            "files": files
        }
    
    def _send_json_response(self, data: dict):
        """Envía una respuesta JSON."""
        response = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
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
    
    def _handle_update_chunk_size(self, data: dict) -> dict:
        """Maneja actualización del tamaño de un chunk."""
        chunk_handle = data.get('chunk_handle')
        size = data.get('size')
        
        if chunk_handle is None or size is None:
            return {"success": False, "message": "Missing chunk_handle or size"}
        
        success = self.master.update_chunk_size(chunk_handle, size)
        return {
            "success": success,
            "message": "Size updated successfully" if success else "Update failed"
        }
    
    def _handle_record_operation(self, data: dict) -> dict:
        """Maneja registro de una operación para métricas."""
        operation_type = data.get('operation_type')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        success = data.get('success', True)
        bytes_transferred = data.get('bytes_transferred', 0)
        chunkserver_id = data.get('chunkserver_id')
        
        if not operation_type or start_time is None or end_time is None:
            return {"success": False, "message": "Missing required fields"}
        
        self.master.operations_tracker.record_operation(
            operation_type=operation_type,
            start_time=start_time,
            end_time=end_time,
            success=success,
            bytes_transferred=bytes_transferred,
            chunkserver_id=chunkserver_id
        )
        
        return {"success": True, "message": "Operation recorded"}
    
    def _handle_get_system_state(self) -> dict:
        """Obtiene el estado completo del sistema."""
        try:
            with self.master._lock:
                # Obtener información de ChunkServers
                chunkservers = {}
                for cs_id, cs_info in self.master.metadata.chunkservers.items():
                    chunkservers[cs_id] = {
                        "id": cs_info.id,
                        "address": cs_info.address,
                        "rack_id": cs_info.rack_id,
                        "is_alive": cs_info.is_alive,
                        "last_heartbeat": cs_info.last_heartbeat.isoformat() if hasattr(cs_info.last_heartbeat, 'isoformat') else str(cs_info.last_heartbeat),
                        "chunks": list(cs_info.chunks)
                    }
                
                # Obtener información de chunks
                chunks = {}
                for chunk_handle, chunk_meta in self.master.metadata.chunks.items():
                    chunks[chunk_handle] = {
                        "handle": chunk_meta.handle,
                        "version": chunk_meta.version,
                        "size": chunk_meta.size,
                        "replicas": [
                            {
                                "chunkserver_id": r.chunkserver_id,
                                "address": r.address
                            }
                            for r in chunk_meta.replicas
                        ],
                        "primary_id": chunk_meta.primary_id,
                        "reference_count": chunk_meta.reference_count
                    }
                
                # Obtener información de archivos
                files = {}
                for path, file_meta in self.master.metadata.files.items():
                    files[path] = {
                        "path": file_meta.path,
                        "chunk_handles": file_meta.chunk_handles,
                        "created_at": file_meta.created_at.isoformat() if hasattr(file_meta.created_at, 'isoformat') else str(file_meta.created_at)
                    }
                
                return {
                    "success": True,
                    "replication_factor": self.master.config.replication_factor,
                    "chunk_size": self.master.config.chunk_size,
                    "chunkservers": chunkservers,
                    "chunks": chunks,
                    "files": files
                }
        except Exception as e:
            # Retornar error en lugar de lanzar excepción
            return {
                "success": False,
                "message": f"Error obteniendo estado del sistema: {str(e)}",
                "chunkservers": {},
                "chunks": {},
                "files": {}
            }
    
    def _handle_get_metrics(self) -> dict:
        """Obtiene métricas actuales del sistema."""
        system_state = self._handle_get_system_state()
        if not system_state.get("success"):
            return system_state
        
        # Calcular métricas básicas
        chunkservers = system_state["chunkservers"]
        chunks = system_state["chunks"]
        replication_factor = system_state["replication_factor"]
        
        chunkservers_alive = sum(1 for cs in chunkservers.values() if cs["is_alive"])
        chunkservers_dead = len(chunkservers) - chunkservers_alive
        
        under_replicated = sum(
            1 for chunk in chunks.values()
            if len(chunk["replicas"]) < replication_factor
        )
        
        # Obtener métricas avanzadas del tracker
        tracker = self.master.operations_tracker
        
        # Throughput (operaciones por segundo)
        throughput = tracker.get_throughput(window_seconds=60.0)
        
        # Latencia (promedio y percentiles)
        latency_all = tracker.get_latency_stats(operation_type=None, window_seconds=60.0)
        latency_read = tracker.get_latency_stats(operation_type='read', window_seconds=60.0)
        latency_write = tracker.get_latency_stats(operation_type='write', window_seconds=60.0)
        latency_append = tracker.get_latency_stats(operation_type='append', window_seconds=60.0)
        
        # Distribución de carga por chunkserver
        chunkserver_load = tracker.get_chunkserver_load()
        
        # Re-replicaciones activas
        active_replications = tracker.get_active_replications()
        
        # Tasa de fallos
        failure_rate = tracker.get_failure_rate(window_seconds=3600.0)
        
        # Fragmentación de archivos
        fragmentation = self.master.get_file_fragmentation_stats()
        
        # Réplicas obsoletas
        stale_replicas = self.master.get_stale_replicas_stats()
        
        return {
            "success": True,
            # Métricas básicas
            "chunkservers_alive": chunkservers_alive,
            "chunkservers_dead": chunkservers_dead,
            "total_chunks": len(chunks),
            "under_replicated_chunks": under_replicated,
            "total_files": len(system_state["files"]),
            # Throughput (operaciones por segundo)
            "throughput": throughput,
            # Latencia (promedio y percentiles)
            "latency": {
                "all": latency_all,
                "read": latency_read,
                "write": latency_write,
                "append": latency_append
            },
            # Distribución de carga por chunkserver
            "chunkserver_load": chunkserver_load,
            # Re-replicaciones activas
            "active_replications": {
                "count": len(active_replications),
                "chunks": list(active_replications.keys())
            },
            # Tasa de fallos (fallos por hora)
            "failure_rate": failure_rate,
            # Fragmentación de archivos
            "fragmentation": fragmentation,
            # Réplicas obsoletas
            "stale_replicas": stale_replicas
        }
    
    def _handle_get_topology(self) -> dict:
        """Obtiene la topología de red del sistema."""
        with self.master._lock:
            # Información del Master
            master_info = {
                "id": "master",
                "address": f"http://{self.master.config.host}:{self.master.config.port}",
                "status": "running",
                "description": "Coordinador central, gestiona metadatos"
            }
            
            # Información de ChunkServers
            chunkservers = []
            for cs_id, cs_info in self.master.metadata.chunkservers.items():
                chunkservers.append({
                    "id": cs_id,
                    "address": cs_info.address,
                    "status": "alive" if cs_info.is_alive else "dead",
                    "chunks_count": len(cs_info.chunks),
                    "rack_id": cs_info.rack_id,
                    "last_heartbeat": cs_info.last_heartbeat.isoformat() if hasattr(cs_info.last_heartbeat, 'isoformat') else str(cs_info.last_heartbeat)
                })
            
            # Conexiones
            connections = []
            for cs in chunkservers:
                connections.append({
                    "from": "master",
                    "to": cs["id"],
                    "type": "heartbeat",
                    "description": "Comunicación de heartbeat y registro"
                })
            
            return {
                "success": True,
                "master": master_info,
                "chunkservers": chunkservers,
                "connections": connections
            }
    
    def _handle_get_chunk_distribution(self, file_path: Optional[str] = None) -> dict:
        """Obtiene la distribución de chunks."""
        with self.master._lock:
            chunks_data = []
            chunkservers_stats = {}
            
            # Inicializar estadísticas de ChunkServers
            for cs_id in self.master.metadata.chunkservers.keys():
                chunkservers_stats[cs_id] = {
                    "total_chunks": 0,
                    "chunks": []
                }
            
            # Filtrar por archivo si se especifica
            relevant_chunks = {}
            if file_path:
                file_meta = self.master.metadata.get_file(file_path)
                if file_meta:
                    for chunk_handle in file_meta.chunk_handles:
                        if chunk_handle:
                            chunk_meta = self.master.metadata.get_chunk_locations(chunk_handle)
                            if chunk_meta:
                                relevant_chunks[chunk_handle] = chunk_meta
            else:
                relevant_chunks = self.master.metadata.chunks
            
            # Procesar chunks
            under_replicated_count = 0
            replication_factor = self.master.config.replication_factor
            
            for chunk_handle, chunk_meta in relevant_chunks.items():
                replicas_count = len(chunk_meta.replicas)
                is_under_replicated = replicas_count < replication_factor
                
                if is_under_replicated:
                    under_replicated_count += 1
                
                # Obtener archivo(s) que usan este chunk
                file_paths = []
                for path, file_meta in self.master.metadata.files.items():
                    if chunk_handle in file_meta.chunk_handles:
                        file_paths.append(path)
                
                chunk_data = {
                    "handle": chunk_handle,
                    "file_path": file_paths[0] if file_paths else None,
                    "file_paths": file_paths,
                    "chunkservers": [r.chunkserver_id for r in chunk_meta.replicas],
                    "size": chunk_meta.size,
                    "version": chunk_meta.version,
                    "replication_status": "complete" if not is_under_replicated else "under_replicated",
                    "replicas_count": replicas_count,
                    "replication_factor": replication_factor
                }
                chunks_data.append(chunk_data)
                
                # Actualizar estadísticas de ChunkServers
                for replica in chunk_meta.replicas:
                    if replica.chunkserver_id in chunkservers_stats:
                        chunkservers_stats[replica.chunkserver_id]["total_chunks"] += 1
                        chunkservers_stats[replica.chunkserver_id]["chunks"].append(chunk_handle)
            
            return {
                "success": True,
                "chunks": chunks_data,
                "summary": {
                    "total_chunks": len(chunks_data),
                    "chunkservers_stats": chunkservers_stats,
                    "under_replicated_count": under_replicated_count,
                    "replication_factor": replication_factor
                },
                "file_path": file_path
            }
    
    def log_message(self, format, *args):
        """Override para logging personalizado."""
        print(f"[Master API] {format % args}")


def create_master_api_handler(master: Master):
    """Factory function para crear handlers con referencia al master."""
    def handler(*args, **kwargs):
        return MasterAPIHandler(master, *args, **kwargs)
    return handler


def run_master_server(master: Master, host: str = "localhost", port: int = 8000):
    """
    Crea y retorna el servidor HTTP del Master con threading para manejar
    peticiones concurrentes.
    
    Args:
        master: Instancia del Master
        host: Dirección del servidor
        port: Puerto del servidor
    
    Returns:
        El servidor creado para permitir su cierre desde fuera
    """
    handler = create_master_api_handler(master)
    # Usar ReusableThreadingTCPServer para permitir reutilización del puerto
    server = ReusableThreadingTCPServer((host, port), handler)
    
    print(f"Master API server iniciado en http://{host}:{port}")
    
    return server

