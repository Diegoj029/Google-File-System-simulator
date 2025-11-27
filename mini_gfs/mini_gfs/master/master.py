"""
Proceso Master del mini-GFS.

El Master es el coordinador central que:
- Mantiene metadatos en memoria
- Coordina operaciones de archivos
- Gestiona réplicas y leases
- Detecta fallos y coordina re-replicación
"""
import threading
import time
from typing import List, Optional

from .metadata import MasterMetadata
from ..common.config import MasterConfig, load_master_config
from ..common.types import ChunkHandle, ChunkLocation


class Master:
    """
    Proceso Master del sistema.
    
    Similar al Master en GFS, coordina todas las operaciones
    y mantiene la vista global del sistema.
    """
    
    def __init__(self, config: Optional[MasterConfig] = None):
        self.config = config or load_master_config()
        self.metadata = MasterMetadata(self.config)
        self.running = False
        self._background_thread = None
        self._lock = threading.RLock()  # Usar RLock para permitir llamadas reentrantes
        
        # Cargar snapshot si existe
        self.metadata.load_snapshot()
    
    def start(self):
        """Inicia el Master y el thread de background para tareas periódicas."""
        if self.running:
            return
        
        self.running = True
        self._background_thread = threading.Thread(target=self._background_worker, daemon=True)
        self._background_thread.start()
        print(f"Master iniciado en {self.config.host}:{self.config.port}")
    
    def stop(self):
        """Detiene el Master."""
        self.running = False
        if self._background_thread:
            self._background_thread.join(timeout=5)
        self.metadata.save_snapshot()
        # Cerrar WAL para asegurar que todos los datos estén escritos
        self.metadata.wal.close()
        print("Master detenido")
    
    def _background_worker(self):
        """
        Thread de background que ejecuta tareas periódicas:
        - Detección de chunkservers muertos
        - Re-replicación de chunks
        - Guardado periódico de snapshot
        - Garbage collection
        """
        last_snapshot_time = time.time()
        last_gc_time = time.time()
        snapshot_interval = 60  # Guardar snapshot cada 60 segundos
        gc_interval = 3600  # Garbage collection cada hora
        
        while self.running:
            try:
                # Detectar chunkservers muertos
                dead_chunkservers = self.metadata.detect_dead_chunkservers()
                if dead_chunkservers:
                    print(f"ChunkServers muertos detectados: {dead_chunkservers}")
                
                # Identificar chunks que necesitan re-replicación
                chunks_needing_replication = self.metadata.get_chunks_needing_replication()
                
                # Intentar re-replicar (en un thread separado para no bloquear)
                if chunks_needing_replication:
                    print(f"Chunks que necesitan re-replicación: {len(chunks_needing_replication)}")
                    # Limitar a 2 por iteración y hacerlo en threads separados
                    for chunk_handle in chunks_needing_replication[:2]:
                        # Hacer re-replicación en thread separado para no bloquear
                        thread = threading.Thread(
                            target=self._attempt_replication,
                            args=(chunk_handle,),
                            daemon=True
                        )
                        thread.start()
                
                # Garbage collection periódico
                current_time = time.time()
                if current_time - last_gc_time >= gc_interval:
                    with self._lock:
                        # Marcar chunks huérfanos
                        newly_marked = self.metadata.garbage_collect_chunks()
                        if newly_marked:
                            print(f"Chunks marcados como garbage: {len(newly_marked)}")
                        
                        # Eliminar chunks marcados hace más de 3 días
                        to_delete = self.metadata.get_garbage_chunks_to_delete(garbage_retention_days=3)
                        for chunk_handle in to_delete:
                            self._delete_chunk_from_chunkservers(chunk_handle)
                            self.metadata.delete_chunk(chunk_handle)
                        if to_delete:
                            print(f"Chunks eliminados: {len(to_delete)}")
                    
                    last_gc_time = current_time
                
                # Guardar snapshot periódicamente
                if current_time - last_snapshot_time >= snapshot_interval:
                    self.metadata.save_snapshot()
                    last_snapshot_time = current_time
                
                time.sleep(5)  # Ejecutar cada 5 segundos
            except Exception as e:
                print(f"Error en background worker: {e}")
                time.sleep(5)
    
    def get_available_chunkservers(self) -> List[str]:
        """Retorna lista de IDs de chunkservers vivos."""
        with self._lock:
            return [
                cs_id for cs_id, cs_info in self.metadata.chunkservers.items()
                if cs_info.is_alive
            ]
    
    def create_file(self, path: str) -> bool:
        """Crea un nuevo archivo."""
        with self._lock:
            return self.metadata.create_file(path)
    
    def get_file_info(self, path: str):
        """Obtiene información de un archivo."""
        with self._lock:
            file_meta = self.metadata.get_file(path)
            if not file_meta:
                return None
            
            chunks_info = []
            for chunk_handle in file_meta.chunk_handles:
                if chunk_handle:
                    chunk_meta = self.metadata.get_chunk_locations(chunk_handle)
                    if chunk_meta:
                        chunks_info.append({
                            "chunk_handle": chunk_handle,
                            "replicas": [
                                {
                                    "chunkserver_id": r.chunkserver_id,
                                    "address": r.address
                                }
                                for r in chunk_meta.replicas
                            ],
                            "primary_id": chunk_meta.primary_id,
                            "size": chunk_meta.size
                        })
            
            return {
                "path": file_meta.path,
                "chunk_handles": file_meta.chunk_handles,
                "chunks_info": chunks_info
            }
    
    def allocate_chunk(self, path: str, chunk_index: int) -> tuple[Optional[ChunkHandle], List[ChunkLocation], Optional[str]]:
        """
        Asigna un nuevo chunk a un archivo.
        
        Retorna (chunk_handle, replicas, primary_id) o (None, [], None) si falla.
        """
        with self._lock:
            # Obtener chunkservers disponibles directamente sin llamar a get_available_chunkservers
            # para evitar doble lock (aunque RLock lo permite, es más eficiente así)
            available_chunkservers = [
                cs_id for cs_id, cs_info in self.metadata.chunkservers.items()
                if cs_info.is_alive
            ]
            
            chunk_handle = self.metadata.allocate_chunk(path, chunk_index, available_chunkservers)
            
            if not chunk_handle:
                return (None, [], None)
            
            chunk_meta = self.metadata.get_chunk_locations(chunk_handle)
            primary_id = self.metadata.get_or_grant_lease(chunk_handle)
            
            return (chunk_handle, chunk_meta.replicas, primary_id)
    
    def get_chunk_locations(self, chunk_handle: ChunkHandle):
        """Obtiene ubicaciones de un chunk y otorga/renueva lease si es necesario."""
        with self._lock:
            chunk_meta = self.metadata.get_chunk_locations(chunk_handle)
            if not chunk_meta:
                return None
            
            primary_id = self.metadata.get_or_grant_lease(chunk_handle)
            chunk_meta.primary_id = primary_id
            
            return {
                "chunk_handle": chunk_handle,
                "replicas": [
                    {
                        "chunkserver_id": r.chunkserver_id,
                        "address": r.address
                    }
                    for r in chunk_meta.replicas
                ],
                "primary_id": primary_id
            }
    
    def register_chunkserver(self, chunkserver_id: str, address: str, chunks: List[ChunkHandle], rack_id: str = "default") -> bool:
        """Registra un ChunkServer."""
        with self._lock:
            # Guardar rack_id temporalmente para que register_chunkserver lo use
            self.metadata._last_rack_id = rack_id
            result = self.metadata.register_chunkserver(chunkserver_id, address, chunks)
            # Actualizar rack_id si el chunkserver ya existía
            if chunkserver_id in self.metadata.chunkservers:
                self.metadata.chunkservers[chunkserver_id].rack_id = rack_id
            return result
    
    def handle_heartbeat(self, chunkserver_id: str, chunks: List[ChunkHandle]) -> bool:
        """Procesa un heartbeat de un ChunkServer."""
        with self._lock:
            return self.metadata.handle_heartbeat(chunkserver_id, chunks)
    
    def _attempt_replication(self, chunk_handle: ChunkHandle):
        """
        Intenta re-replicar un chunk que tiene menos réplicas de las requeridas.
        
        Selecciona un chunkserver fuente y destino, y coordina la clonación.
        """
        import requests
        
        with self._lock:
            source_id, target_id = self.metadata.select_source_and_target_for_replication(chunk_handle)
            
            if not source_id or not target_id:
                return
            
            # Obtener direcciones
            source_cs = self.metadata.chunkservers.get(source_id)
            target_cs = self.metadata.chunkservers.get(target_id)
            
            if not source_cs or not target_cs:
                return
            
            source_address = source_cs.address
            target_address = target_cs.address
        
        # Solicitar clonación al chunkserver destino
        try:
            response = requests.post(
                f"{target_address}/clone_chunk",
                json={
                    "chunk_handle": chunk_handle,
                    "src_address": source_address
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"Chunk {chunk_handle} re-replicado desde {source_id} a {target_id}")
                    # Actualizar metadatos (el próximo heartbeat actualizará la lista)
                else:
                    print(f"Error re-replicando chunk {chunk_handle}: {result.get('message')}")
        except Exception as e:
            print(f"Error re-replicando chunk {chunk_handle}: {e}")
    
    def _delete_chunk_from_chunkservers(self, chunk_handle: ChunkHandle):
        """Envía comando de eliminación a todos los ChunkServers que tienen el chunk."""
        import requests
        
        with self._lock:
            chunk_meta = self.metadata.get_chunk_locations(chunk_handle)
            if not chunk_meta:
                return
            
            for replica in chunk_meta.replicas:
                try:
                    response = requests.post(
                        f"{replica.address}/delete_chunk",
                        json={"chunk_handle": chunk_handle},
                        timeout=10
                    )
                    if response.status_code == 200:
                        result = response.json()
                        if not result.get("success"):
                            print(f"Warning: Error eliminando chunk {chunk_handle} de {replica.chunkserver_id}")
                except Exception as e:
                    print(f"Error eliminando chunk {chunk_handle} de {replica.chunkserver_id}: {e}")
    
    def snapshot_file(self, source_path: str, dest_path: str) -> bool:
        """Crea un snapshot de un archivo."""
        with self._lock:
            return self.metadata.snapshot_file(source_path, dest_path)
    
    def rename_file(self, old_path: str, new_path: str) -> bool:
        """Renombra un archivo."""
        with self._lock:
            return self.metadata.rename_file(old_path, new_path)
    
    def delete_file(self, path: str) -> bool:
        """Elimina un archivo."""
        with self._lock:
            return self.metadata.delete_file(path)
    
    def list_directory(self, dir_path: str = "/") -> List[str]:
        """Lista archivos en un directorio."""
        with self._lock:
            return self.metadata.list_directory(dir_path)

