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
from typing import List, Optional, Dict

from .metadata import MasterMetadata
from .operations_tracker import OperationsTracker
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
        self.operations_tracker = OperationsTracker()
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
                    # Registrar fallos en el tracker
                    for cs_id in dead_chunkservers:
                        self.operations_tracker.record_chunkserver_failure(cs_id)
                
                # Identificar chunks que necesitan re-replicación
                chunks_needing_replication = self.metadata.get_chunks_needing_replication()
                
                # Intentar re-replicar (en un thread separado para no bloquear)
                if chunks_needing_replication:
                    print(f"Chunks que necesitan re-replicación: {len(chunks_needing_replication)}")
                    # Limitar a 2 por iteración y hacerlo en threads separados
                    for chunk_handle in chunks_needing_replication[:2]:
                        # Registrar inicio de re-replicación
                        self.operations_tracker.start_replication(chunk_handle)
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
                "primary_id": primary_id,
                "size": chunk_meta.size,
                "reference_count": chunk_meta.reference_count
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
            
            # Mostrar mensaje de registro exitoso
            if result:
                print(f"[Master] ChunkServer {chunkserver_id} registrado")
            
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
                    # Registrar fin de re-replicación
                    self.operations_tracker.end_replication(chunk_handle)
                    # Actualizar metadatos (el próximo heartbeat actualizará la lista)
                else:
                    print(f"Error re-replicando chunk {chunk_handle}: {result.get('message')}")
                    self.operations_tracker.end_replication(chunk_handle)
        except Exception as e:
            print(f"Error re-replicando chunk {chunk_handle}: {e}")
            self.operations_tracker.end_replication(chunk_handle)
    
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
    
    def update_chunk_size(self, chunk_handle: ChunkHandle, size: int) -> bool:
        """Actualiza el tamaño de un chunk en los metadatos."""
        with self._lock:
            self.metadata.update_chunk_size(chunk_handle, size)
            return True
    
    def clone_shared_chunk(self, path: str, chunk_index: int, old_chunk_handle: ChunkHandle) -> Optional[ChunkHandle]:
        """
        Clona un chunk compartido para copy-on-write.
        
        Retorna el nuevo chunk_handle, o None si falla.
        """
        import requests
        
        with self._lock:
            available_chunkservers = [
                cs_id for cs_id, cs_info in self.metadata.chunkservers.items()
                if cs_info.is_alive
            ]
            
            # Crear nuevo chunk y actualizar metadatos
            new_chunk_handle = self.metadata.clone_shared_chunk(
                path, chunk_index, old_chunk_handle, available_chunkservers
            )
            
            if not new_chunk_handle:
                return None
            
            # Obtener información de ambos chunks
            old_chunk_meta = self.metadata.get_chunk_locations(old_chunk_handle)
            new_chunk_meta = self.metadata.get_chunk_locations(new_chunk_handle)
            
            if not old_chunk_meta or not new_chunk_meta:
                return None
        
        # Coordinar la clonación del contenido en los chunkservers
        # Cada réplica del nuevo chunk debe clonar desde la réplica correspondiente del chunk original
        old_replicas = {r.chunkserver_id: r for r in old_chunk_meta.replicas}
        
        for new_replica in new_chunk_meta.replicas:
            # Encontrar réplica correspondiente en el chunk original
            old_replica = old_replicas.get(new_replica.chunkserver_id)
            if old_replica:
                # Clonar desde la misma réplica (más eficiente)
                src_address = old_replica.address
            else:
                # Usar la primera réplica disponible del chunk original
                src_address = old_chunk_meta.replicas[0].address if old_chunk_meta.replicas else None
            
            if src_address:
                try:
                    response = requests.post(
                        f"{new_replica.address}/clone_chunk",
                        json={
                            "chunk_handle": new_chunk_handle,
                            "src_address": src_address,
                            "src_chunk_handle": old_chunk_handle
                        },
                        timeout=60
                    )
                    if response.status_code != 200 or not response.json().get("success"):
                        print(f"Warning: Error clonando contenido de chunk {old_chunk_handle} a {new_chunk_handle} en {new_replica.chunkserver_id}")
                except Exception as e:
                    print(f"Warning: Error clonando contenido de chunk: {e}")
        
        return new_chunk_handle
    
    def get_file_fragmentation_stats(self) -> Dict:
        """
        Calcula estadísticas de fragmentación de archivos.
        
        Returns:
            Diccionario con estadísticas de fragmentación:
            {
                'files_by_chunk_count': {num_chunks: count},
                'avg_chunks_per_file': float,
                'max_chunks_per_file': int,
                'total_files': int
            }
        """
        with self._lock:
            files_by_chunk_count = {}
            total_chunks = 0
            max_chunks = 0
            
            for file_meta in self.metadata.files.values():
                num_chunks = len([ch for ch in file_meta.chunk_handles if ch])
                files_by_chunk_count[num_chunks] = files_by_chunk_count.get(num_chunks, 0) + 1
                total_chunks += num_chunks
                max_chunks = max(max_chunks, num_chunks)
            
            total_files = len(self.metadata.files)
            avg_chunks = total_chunks / total_files if total_files > 0 else 0
            
            return {
                'files_by_chunk_count': files_by_chunk_count,
                'avg_chunks_per_file': avg_chunks,
                'max_chunks_per_file': max_chunks,
                'total_files': total_files
            }
    
    def get_stale_replicas_stats(self) -> Dict:
        """
        Calcula estadísticas de réplicas obsoletas (versiones inconsistentes).
        
        Returns:
            Diccionario con estadísticas:
            {
                'chunks_with_stale_replicas': int,
                'total_stale_replicas': int,
                'stale_replicas_by_chunkserver': {cs_id: count}
            }
        """
        with self._lock:
            chunks_with_stale = 0
            total_stale = 0
            stale_by_cs = {}
            
            for chunk_handle, chunk_meta in self.metadata.chunks.items():
                # Obtener versión esperada (la versión del chunk en metadatos)
                expected_version = chunk_meta.version
                
                # Contar réplicas con versión diferente (esto requiere verificar en chunkservers)
                # Por simplicidad, asumimos que si un chunkserver no reporta el chunk en heartbeat,
                # puede ser una réplica obsoleta
                # En un sistema real, se verificaría la versión en cada chunkserver
                live_replicas = [
                    r for r in chunk_meta.replicas
                    if r.chunkserver_id in self.metadata.chunkservers
                    and self.metadata.chunkservers[r.chunkserver_id].is_alive
                    and chunk_handle in self.metadata.chunkserver_chunks.get(r.chunkserver_id, set())
                ]
                
                # Si hay menos réplicas vivas que las esperadas, algunas pueden estar obsoletas
                if len(live_replicas) < len(chunk_meta.replicas):
                    chunks_with_stale += 1
                    stale_count = len(chunk_meta.replicas) - len(live_replicas)
                    total_stale += stale_count
                    
                    # Contar por chunkserver (réplicas que no están vivas)
                    for replica in chunk_meta.replicas:
                        if replica.chunkserver_id not in [r.chunkserver_id for r in live_replicas]:
                            stale_by_cs[replica.chunkserver_id] = \
                                stale_by_cs.get(replica.chunkserver_id, 0) + 1
            
            return {
                'chunks_with_stale_replicas': chunks_with_stale,
                'total_stale_replicas': total_stale,
                'stale_replicas_by_chunkserver': stale_by_cs
            }

