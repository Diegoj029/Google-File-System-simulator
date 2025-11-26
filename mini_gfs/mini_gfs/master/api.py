"""
API HTTP del Master.

Expone endpoints JSON para que ChunkServers y Clients
se comuniquen con el Master.
"""
import json
import base64
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

from .master import Master
from ..common.types import ChunkHandle


class MasterAPIHandler(BaseHTTPRequestHandler):
    """
    Handler HTTP para las peticiones al Master.
    
    Maneja todas las operaciones del Master vía JSON sobre HTTP.
    """
    
    def __init__(self, master: Master, *args, **kwargs):
        self.master = master
        super().__init__(*args, **kwargs)
    
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
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def _handle_register_chunkserver(self, data: dict) -> dict:
        """Maneja registro de ChunkServer."""
        chunkserver_id = data.get('chunkserver_id')
        address = data.get('address')
        chunks = data.get('chunks', [])
        
        if not chunkserver_id or not address:
            return {"success": False, "message": "Missing chunkserver_id or address"}
        
        success = self.master.register_chunkserver(chunkserver_id, address, chunks)
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
            "primary_id": locations["primary_id"]
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
    Inicia el servidor HTTP del Master con threading para manejar
    peticiones concurrentes.
    
    Args:
        master: Instancia del Master
        host: Dirección del servidor
        port: Puerto del servidor
    """
    handler = create_master_api_handler(master)
    # Usar ThreadingTCPServer para manejar peticiones concurrentes
    server = socketserver.ThreadingTCPServer((host, port), handler)
    server.allow_reuse_address = True
    
    print(f"Master API server iniciado en http://{host}:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo Master API server...")
        master.stop()
        server.shutdown()

