"""
Proceso ChunkServer del mini-GFS.

El ChunkServer almacena chunks en disco local y responde
a peticiones de lectura/escritura del Client.
"""
import threading
import time
import uuid
import requests
from typing import List, Optional

from .storage import ChunkStorage
from ..common.config import ChunkServerConfig, load_chunkserver_config
from ..common.types import ChunkHandle


class ChunkServer:
    """
    Proceso ChunkServer.
    
    Similar a los ChunkServers en GFS, almacena chunks en disco
    y se comunica con el Master para registro y heartbeats.
    """
    
    def __init__(self, config: Optional[ChunkServerConfig] = None):
        self.config = config or load_chunkserver_config()
        
        # Generar ID si no está configurado
        if not self.config.chunkserver_id:
            self.config.chunkserver_id = str(uuid.uuid4())[:8]
        
        self.storage = ChunkStorage(self.config.data_dir)
        self.running = False
        self._heartbeat_thread = None
        self._lock = threading.Lock()
        
        # Cargar chunks existentes al iniciar
        self._load_local_chunks()
    
    def _load_local_chunks(self):
        """Carga la lista de chunks almacenados localmente."""
        chunks = self.storage.list_chunks()
        print(f"ChunkServer {self.config.chunkserver_id}: Cargados {len(chunks)} chunks locales")
    
    def start(self):
        """Inicia el ChunkServer y registra con el Master."""
        if self.running:
            return
        
        self.running = True
        
        # Registrar con el Master
        self._register_with_master()
        
        # Iniciar thread de heartbeats
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
        self._heartbeat_thread.start()
        
        print(f"ChunkServer {self.config.chunkserver_id} iniciado en {self.config.host}:{self.config.port}")
    
    def stop(self):
        """Detiene el ChunkServer."""
        self.running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        print(f"ChunkServer {self.config.chunkserver_id} detenido")
    
    def _register_with_master(self) -> bool:
        """Registra este ChunkServer con el Master."""
        chunks = self.storage.list_chunks()
        address = f"http://{self.config.host}:{self.config.port}"
        
        try:
            response = requests.post(
                f"{self.config.master_address}/register_chunkserver",
                json={
                    "chunkserver_id": self.config.chunkserver_id,
                    "address": address,
                    "chunks": chunks,
                    "rack_id": self.config.rack_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"ChunkServer {self.config.chunkserver_id} registrado con Master")
                    return True
            
            print(f"Error registrando ChunkServer: {response.text}")
            return False
        except Exception as e:
            print(f"Error conectando con Master: {e}")
            return False
    
    def _heartbeat_worker(self):
        """Thread que envía heartbeats periódicos al Master."""
        while self.running:
            try:
                chunks = self.storage.list_chunks()
                address = f"http://{self.config.host}:{self.config.port}"
                
                response = requests.post(
                    f"{self.config.master_address}/heartbeat",
                    json={
                        "chunkserver_id": self.config.chunkserver_id,
                        "chunks": chunks
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if not result.get("success"):
                        print(f"Warning: Heartbeat falló: {result.get('message')}")
                else:
                    print(f"Warning: Heartbeat recibió código {response.status_code}")
            except Exception as e:
                print(f"Error enviando heartbeat: {e}")
            
            time.sleep(self.config.heartbeat_interval)
    
    def write_chunk(self, chunk_handle: ChunkHandle, offset: int, data: bytes) -> int:
        """Escribe datos en un chunk."""
        with self._lock:
            return self.storage.write_chunk(chunk_handle, offset, data)
    
    def read_chunk(self, chunk_handle: ChunkHandle, offset: int, length: int) -> Optional[bytes]:
        """Lee datos de un chunk."""
        with self._lock:
            return self.storage.read_chunk(chunk_handle, offset, length)
    
    def append_record(self, chunk_handle: ChunkHandle, data: bytes, chunk_size: int) -> tuple[int, int]:
        """
        Añade un record al final de un chunk.
        
        Retorna (offset, bytes_written) o (-1, 0) si falla.
        """
        with self._lock:
            return self.storage.append_record(chunk_handle, data, chunk_size)
    
    def clone_chunk(self, chunk_handle: ChunkHandle, src_address: str, src_chunk_handle: Optional[ChunkHandle] = None) -> bool:
        """Clona un chunk desde otro ChunkServer."""
        with self._lock:
            return self.storage.clone_chunk(chunk_handle, src_address, src_chunk_handle)
    
    def get_chunk_size(self, chunk_handle: ChunkHandle) -> int:
        """Retorna el tamaño de un chunk."""
        return self.storage.get_chunk_size(chunk_handle)
    
    def list_chunks(self) -> List[ChunkHandle]:
        """Retorna lista de chunks almacenados localmente."""
        return self.storage.list_chunks()
    
    def delete_chunk(self, chunk_handle: ChunkHandle) -> bool:
        """Elimina un chunk localmente."""
        with self._lock:
            return self.storage.delete_chunk(chunk_handle)

