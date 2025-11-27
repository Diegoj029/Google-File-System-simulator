"""
API HTTP del ChunkServer.

Expone endpoints JSON para que Clients y otros ChunkServers
se comuniquen con este ChunkServer.
"""
import json
import base64
import socket
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from .chunkserver import ChunkServer
from ..common.config import MasterConfig


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    """ThreadingTCPServer con SO_REUSEADDR habilitado para reutilizar puertos."""
    allow_reuse_address = True
    
    def server_bind(self):
        """Configura el socket con SO_REUSEADDR antes de hacer bind."""
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class ChunkServerAPIHandler(BaseHTTPRequestHandler):
    """
    Handler HTTP para las peticiones al ChunkServer.
    
    Maneja operaciones de lectura, escritura, append y clonación.
    """
    
    def __init__(self, chunkserver: ChunkServer, chunk_size: int, *args, **kwargs):
        self.chunkserver = chunkserver
        self.chunk_size = chunk_size
        super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """Maneja todas las peticiones POST."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
                return
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            # Cliente cerró la conexión antes de completar la petición
            return
        
        path = urlparse(self.path).path
        
        # Enrutar según el path
        if path == '/write_chunk':
            response = self._handle_write_chunk(data)
        elif path == '/read_chunk':
            response = self._handle_read_chunk(data)
        elif path == '/append_record':
            response = self._handle_append_record(data)
        elif path == '/clone_chunk':
            response = self._handle_clone_chunk(data)
        elif path == '/delete_chunk':
            response = self._handle_delete_chunk(data)
        elif path == '/write_chunk_pipeline':
            response = self._handle_write_chunk_pipeline(data)
        else:
            self._send_error(404, f"Unknown endpoint: {path}")
            return
        
        self._send_json_response(response)
    
    def _handle_write_chunk(self, data: dict) -> dict:
        """Maneja escritura en chunk."""
        chunk_handle = data.get('chunk_handle')
        offset = data.get('offset')
        data_b64 = data.get('data')
        
        if chunk_handle is None or offset is None or data_b64 is None:
            return {"success": False, "message": "Missing required fields"}
        
        try:
            # Decodificar datos desde base64
            chunk_data = base64.b64decode(data_b64)
        except Exception as e:
            return {"success": False, "message": f"Invalid base64 data: {e}"}
        
        bytes_written = self.chunkserver.write_chunk(chunk_handle, offset, chunk_data)
        
        # Obtener tamaño actual del chunk después de escribir
        current_size = self.chunkserver.get_chunk_size(chunk_handle)
        
        return {
            "success": True,
            "message": "Write successful",
            "bytes_written": bytes_written,
            "chunk_size": current_size
        }
    
    def _handle_read_chunk(self, data: dict) -> dict:
        """Maneja lectura de chunk."""
        chunk_handle = data.get('chunk_handle')
        offset = data.get('offset', 0)
        length = data.get('length')
        
        if chunk_handle is None or length is None:
            return {"success": False, "message": "Missing chunk_handle or length"}
        
        chunk_data = self.chunkserver.read_chunk(chunk_handle, offset, length)
        
        if chunk_data is None:
            return {"success": False, "message": "Chunk not found"}
        
        # Codificar datos en base64 para JSON
        data_b64 = base64.b64encode(chunk_data).decode('utf-8')
        
        return {
            "success": True,
            "data": data_b64,
            "bytes_read": len(chunk_data)
        }
    
    def _handle_append_record(self, data: dict) -> dict:
        """Maneja append de record."""
        chunk_handle = data.get('chunk_handle')
        data_b64 = data.get('data')
        
        if chunk_handle is None or data_b64 is None:
            return {"success": False, "message": "Missing required fields"}
        
        try:
            # Decodificar datos desde base64
            record_data = base64.b64decode(data_b64)
        except Exception as e:
            return {"success": False, "message": f"Invalid base64 data: {e}"}
        
        offset, bytes_written = self.chunkserver.append_record(
            chunk_handle, record_data, self.chunk_size
        )
        
        if offset < 0:
            return {
                "success": False,
                "message": "Chunk is full, cannot append"
            }
        
        return {
            "success": True,
            "message": "Append successful",
            "offset": offset,
            "bytes_written": bytes_written
        }
    
    def _handle_clone_chunk(self, data: dict) -> dict:
        """Maneja clonación de chunk desde otro ChunkServer."""
        chunk_handle = data.get('chunk_handle')
        src_address = data.get('src_address')
        src_chunk_handle = data.get('src_chunk_handle')  # Opcional, para copy-on-write
        
        if chunk_handle is None or src_address is None:
            return {"success": False, "message": "Missing chunk_handle or src_address"}
        
        success = self.chunkserver.clone_chunk(chunk_handle, src_address, src_chunk_handle)
        
        return {
            "success": success,
            "message": "Clone successful" if success else "Clone failed"
        }
    
    def _handle_delete_chunk(self, data: dict) -> dict:
        """Maneja eliminación de chunk."""
        chunk_handle = data.get('chunk_handle')
        
        if chunk_handle is None:
            return {"success": False, "message": "Missing chunk_handle"}
        
        success = self.chunkserver.delete_chunk(chunk_handle)
        
        return {
            "success": success,
            "message": "Chunk deleted" if success else "Delete failed"
        }
    
    def _handle_write_chunk_pipeline(self, data: dict) -> dict:
        """Maneja escritura en chunk desde pipeline (otro ChunkServer)."""
        chunk_handle = data.get('chunk_handle')
        offset = data.get('offset')
        data_b64 = data.get('data')
        src_address = data.get('src_address')  # Opcional: para pipeline
        
        if chunk_handle is None or offset is None or data_b64 is None:
            return {"success": False, "message": "Missing required fields"}
        
        try:
            chunk_data = base64.b64decode(data_b64)
        except Exception as e:
            return {"success": False, "message": f"Invalid base64 data: {e}"}
        
        bytes_written = self.chunkserver.write_chunk(chunk_handle, offset, chunk_data)
        
        # Obtener tamaño actual del chunk después de escribir
        current_size = self.chunkserver.get_chunk_size(chunk_handle)
        
        return {
            "success": True,
            "message": "Write successful",
            "bytes_written": bytes_written,
            "chunk_size": current_size
        }
    
    def _send_json_response(self, data: dict):
        """Envía una respuesta JSON."""
        try:
            response = json.dumps(data).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            # Cliente cerró la conexión antes de recibir la respuesta
            # Esto es normal y no requiere logging de error
            pass
    
    def _send_error(self, code: int, message: str):
        """Envía un error HTTP."""
        try:
            response = json.dumps({"success": False, "message": message}).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            # Cliente cerró la conexión antes de recibir la respuesta
            # Esto es normal y no requiere logging de error
            pass
    
    def log_message(self, format, *args):
        """Override para logging personalizado."""
        print(f"[ChunkServer {self.chunkserver.config.chunkserver_id} API] {format % args}")


def create_chunkserver_api_handler(chunkserver: ChunkServer, chunk_size: int):
    """Factory function para crear handlers con referencia al chunkserver."""
    def handler(*args, **kwargs):
        return ChunkServerAPIHandler(chunkserver, chunk_size, *args, **kwargs)
    return handler


def run_chunkserver_server(chunkserver: ChunkServer, chunk_size: int, 
                          host: str = "localhost", port: int = 8001):
    """
    Inicia el servidor HTTP del ChunkServer con threading para manejar
    peticiones concurrentes.
    
    Args:
        chunkserver: Instancia del ChunkServer
        chunk_size: Tamaño máximo de chunks
        host: Dirección del servidor
        port: Puerto del servidor
    """
    handler = create_chunkserver_api_handler(chunkserver, chunk_size)
    # Usar ReusableThreadingTCPServer para manejar peticiones concurrentes
    # y permitir reutilización de puertos
    server = ReusableThreadingTCPServer((host, port), handler)
    
    print(f"ChunkServer API server iniciado en http://{host}:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nDeteniendo ChunkServer {chunkserver.config.chunkserver_id} API server...")
        chunkserver.stop()
        server.shutdown()

