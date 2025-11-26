"""
Gestión de metadatos del Master.

Mantiene en memoria:
- Namespace de archivos (file_path -> FileMetadata)
- Mapeo de chunks (chunk_handle -> ChunkMetadata)
- Información de ChunkServers
- Leases activos

También maneja la persistencia periódica a disco (JSON snapshot).
"""
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from ..common.types import (
    ChunkHandle, FileMetadata, ChunkMetadata, ChunkLocation,
    LeaseInfo, ChunkServerInfo
)
from ..common.config import MasterConfig


class MasterMetadata:
    """
    Gestor de metadatos del Master.
    
    Similar al NameNode en HDFS o al Master en GFS, mantiene
    toda la información sobre archivos, chunks y réplicas en memoria.
    """
    
    def __init__(self, config: MasterConfig):
        self.config = config
        
        # Namespace: path -> FileMetadata
        self.files: Dict[str, FileMetadata] = {}
        
        # Chunks: chunk_handle -> ChunkMetadata
        self.chunks: Dict[ChunkHandle, ChunkMetadata] = {}
        
        # ChunkServers: chunkserver_id -> ChunkServerInfo
        self.chunkservers: Dict[str, ChunkServerInfo] = {}
        
        # Leases: chunk_handle -> LeaseInfo
        self.leases: Dict[ChunkHandle, LeaseInfo] = {}
        
        # Índice inverso: chunkserver_id -> set de chunk_handles
        self.chunkserver_chunks: Dict[str, set] = defaultdict(set)
        
        # Asegurar que el directorio de metadatos existe
        self.metadata_dir = Path(config.metadata_dir)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.metadata_dir / config.snapshot_file
    
    def create_file(self, path: str) -> bool:
        """
        Crea un nuevo archivo en el namespace.
        
        Retorna True si se creó exitosamente, False si ya existe.
        """
        if path in self.files:
            return False
        
        self.files[path] = FileMetadata(path=path)
        return True
    
    def get_file(self, path: str) -> Optional[FileMetadata]:
        """Obtiene los metadatos de un archivo."""
        return self.files.get(path)
    
    def allocate_chunk(self, path: str, chunk_index: int, 
                      available_chunkservers: List[str]) -> Optional[ChunkHandle]:
        """
        Asigna un nuevo chunk a un archivo.
        
        Args:
            path: Ruta del archivo
            chunk_index: Índice del chunk en la lista de chunks del archivo
            available_chunkservers: Lista de IDs de chunkservers disponibles
        
        Retorna:
            ChunkHandle del nuevo chunk, o None si falla
        """
        file_meta = self.files.get(path)
        if not file_meta:
            return None
        
        # Generar nuevo chunk handle
        chunk_handle = str(uuid.uuid4())
        
        # Seleccionar réplicas (hasta replication_factor)
        num_replicas = min(self.config.replication_factor, len(available_chunkservers))
        if num_replicas == 0:
            return None
        
        replica_locations = []
        for i in range(num_replicas):
            cs_id = available_chunkservers[i % len(available_chunkservers)]
            cs_info = self.chunkservers.get(cs_id)
            if cs_info and cs_info.is_alive:
                replica_locations.append(ChunkLocation(
                    chunkserver_id=cs_id,
                    address=cs_info.address
                ))
        
        if not replica_locations:
            return None
        
        # Crear metadatos del chunk
        chunk_meta = ChunkMetadata(
            handle=chunk_handle,
            replicas=replica_locations,
            primary_id=replica_locations[0].chunkserver_id  # Primer replica como primary inicial
        )
        
        self.chunks[chunk_handle] = chunk_meta
        
        # Agregar chunk al archivo
        while len(file_meta.chunk_handles) <= chunk_index:
            file_meta.chunk_handles.append(None)
        file_meta.chunk_handles[chunk_index] = chunk_handle
        
        # Actualizar índice inverso
        for loc in replica_locations:
            self.chunkserver_chunks[loc.chunkserver_id].add(chunk_handle)
        
        return chunk_handle
    
    def get_chunk_locations(self, chunk_handle: ChunkHandle) -> Optional[ChunkMetadata]:
        """Obtiene las ubicaciones de un chunk."""
        return self.chunks.get(chunk_handle)
    
    def register_chunkserver(self, chunkserver_id: str, address: str, 
                            chunks: List[ChunkHandle]) -> bool:
        """
        Registra un ChunkServer con el Master.
        
        Actualiza la información del chunkserver y sincroniza
        los chunks que reporta tener.
        """
        # Crear o actualizar información del chunkserver
        if chunkserver_id in self.chunkservers:
            cs_info = self.chunkservers[chunkserver_id]
            cs_info.address = address
            cs_info.last_heartbeat = datetime.now()
            cs_info.is_alive = True
        else:
            cs_info = ChunkServerInfo(
                id=chunkserver_id,
                address=address,
                chunks=chunks.copy()
            )
            self.chunkservers[chunkserver_id] = cs_info
        
        # Actualizar chunks reportados por este chunkserver
        old_chunks = self.chunkserver_chunks[chunkserver_id]
        new_chunks = set(chunks)
        
        # Chunks que ya no tiene (remover de réplicas)
        for chunk_handle in old_chunks - new_chunks:
            chunk_meta = self.chunks.get(chunk_handle)
            if chunk_meta:
                chunk_meta.replicas = [
                    r for r in chunk_meta.replicas 
                    if r.chunkserver_id != chunkserver_id
                ]
                # Si era primary y ya no está, invalidar lease
                if chunk_meta.primary_id == chunkserver_id:
                    chunk_meta.primary_id = None
                    if chunk_handle in self.leases:
                        del self.leases[chunk_handle]
        
        # Chunks nuevos (agregar a réplicas)
        for chunk_handle in new_chunks - old_chunks:
            chunk_meta = self.chunks.get(chunk_handle)
            if chunk_meta:
                # Verificar si ya está en las réplicas
                if not any(r.chunkserver_id == chunkserver_id 
                          for r in chunk_meta.replicas):
                    chunk_meta.replicas.append(ChunkLocation(
                        chunkserver_id=chunkserver_id,
                        address=address
                    ))
        
        # Actualizar índice inverso
        self.chunkserver_chunks[chunkserver_id] = new_chunks
        cs_info.chunks = chunks.copy()
        
        return True
    
    def handle_heartbeat(self, chunkserver_id: str, chunks: List[ChunkHandle]) -> bool:
        """
        Procesa un heartbeat de un ChunkServer.
        
        Similar a register_chunkserver, pero específico para heartbeats periódicos.
        """
        if chunkserver_id not in self.chunkservers:
            return False
        
        cs_info = self.chunkservers[chunkserver_id]
        cs_info.last_heartbeat = datetime.now()
        cs_info.is_alive = True
        
        # Actualizar lista de chunks
        self.chunkserver_chunks[chunkserver_id] = set(chunks)
        cs_info.chunks = chunks.copy()
        
        return True
    
    def get_or_grant_lease(self, chunk_handle: ChunkHandle) -> Optional[str]:
        """
        Obtiene o otorga un lease para un chunk.
        
        Retorna el ID del chunkserver que es primary, o None si no hay réplicas vivas.
        """
        chunk_meta = self.chunks.get(chunk_handle)
        if not chunk_meta:
            return None
        
        # Verificar si hay un lease válido
        if chunk_handle in self.leases:
            lease = self.leases[chunk_handle]
            if lease.expiration > datetime.now():
                # Verificar que el primary sigue vivo
                if lease.primary_id in self.chunkservers:
                    cs_info = self.chunkservers[lease.primary_id]
                    if cs_info.is_alive and chunk_handle in self.chunkserver_chunks[lease.primary_id]:
                        return lease.primary_id
        
        # No hay lease válido, otorgar uno nuevo
        # Seleccionar primary de las réplicas vivas
        live_replicas = [
            r for r in chunk_meta.replicas
            if r.chunkserver_id in self.chunkservers
            and self.chunkservers[r.chunkserver_id].is_alive
            and chunk_handle in self.chunkserver_chunks[r.chunkserver_id]
        ]
        
        if not live_replicas:
            return None
        
        primary_id = live_replicas[0].chunkserver_id
        chunk_meta.primary_id = primary_id
        
        # Crear nuevo lease
        lease = LeaseInfo(
            chunk_handle=chunk_handle,
            primary_id=primary_id,
            expiration=datetime.now() + timedelta(seconds=self.config.lease_duration)
        )
        self.leases[chunk_handle] = lease
        
        return primary_id
    
    def detect_dead_chunkservers(self) -> List[str]:
        """
        Detecta ChunkServers que no han enviado heartbeat recientemente.
        
        Retorna lista de IDs de chunkservers muertos.
        """
        dead = []
        timeout = timedelta(seconds=self.config.heartbeat_timeout)
        now = datetime.now()
        
        for cs_id, cs_info in self.chunkservers.items():
            if cs_info.is_alive and (now - cs_info.last_heartbeat) > timeout:
                cs_info.is_alive = False
                dead.append(cs_id)
        
        return dead
    
    def get_chunks_needing_replication(self) -> List[ChunkHandle]:
        """
        Identifica chunks que tienen menos réplicas de las requeridas.
        
        Retorna lista de chunk handles que necesitan re-replicación.
        """
        needing_replication = []
        
        for chunk_handle, chunk_meta in self.chunks.items():
            # Contar réplicas vivas
            live_replicas = [
                r for r in chunk_meta.replicas
                if r.chunkserver_id in self.chunkservers
                and self.chunkservers[r.chunkserver_id].is_alive
                and chunk_handle in self.chunkserver_chunks[r.chunkserver_id]
            ]
            
            if len(live_replicas) < self.config.replication_factor:
                needing_replication.append(chunk_handle)
        
        return needing_replication
    
    def select_source_and_target_for_replication(
        self, chunk_handle: ChunkHandle
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Selecciona un chunkserver fuente y destino para re-replicación.
        
        Retorna (source_chunkserver_id, target_chunkserver_id) o (None, None) si no es posible.
        """
        chunk_meta = self.chunks.get(chunk_handle)
        if not chunk_meta:
            return (None, None)
        
        # Encontrar una réplica viva como fuente
        source_id = None
        for replica in chunk_meta.replicas:
            if (replica.chunkserver_id in self.chunkservers
                and self.chunkservers[replica.chunkserver_id].is_alive
                and chunk_handle in self.chunkserver_chunks[replica.chunkserver_id]):
                source_id = replica.chunkserver_id
                break
        
        if not source_id:
            return (None, None)
        
        # Encontrar un chunkserver destino que no tenga este chunk
        target_id = None
        for cs_id, cs_info in self.chunkservers.items():
            if (cs_info.is_alive 
                and cs_id != source_id
                and chunk_handle not in self.chunkserver_chunks[cs_id]):
                target_id = cs_id
                break
        
        return (source_id, target_id)
    
    def save_snapshot(self) -> bool:
        """
        Guarda un snapshot de los metadatos a disco (JSON).
        
        En GFS real, esto se hace de forma más sofisticada con logs y checkpoints.
        Aquí simplificamos a un solo archivo JSON.
        """
        try:
            snapshot = {
                "files": {
                    path: {
                        "path": file_meta.path,
                        "chunk_handles": file_meta.chunk_handles,
                        "created_at": file_meta.created_at.isoformat()
                    }
                    for path, file_meta in self.files.items()
                },
                "chunks": {
                    handle: {
                        "handle": chunk_meta.handle,
                        "replicas": [
                            {
                                "chunkserver_id": r.chunkserver_id,
                                "address": r.address
                            }
                            for r in chunk_meta.replicas
                        ],
                        "primary_id": chunk_meta.primary_id,
                        "size": chunk_meta.size
                    }
                    for handle, chunk_meta in self.chunks.items()
                },
                "chunkservers": {
                    cs_id: {
                        "id": cs_info.id,
                        "address": cs_info.address,
                        "chunks": cs_info.chunks,
                        "last_heartbeat": cs_info.last_heartbeat.isoformat(),
                        "is_alive": cs_info.is_alive
                    }
                    for cs_id, cs_info in self.chunkservers.items()
                },
                "snapshot_time": datetime.now().isoformat()
            }
            
            with open(self.snapshot_path, 'w') as f:
                json.dump(snapshot, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error guardando snapshot: {e}")
            return False
    
    def load_snapshot(self) -> bool:
        """
        Carga metadatos desde un snapshot en disco.
        
        Retorna True si se cargó exitosamente, False en caso contrario.
        """
        if not self.snapshot_path.exists():
            return False
        
        try:
            with open(self.snapshot_path, 'r') as f:
                snapshot = json.load(f)
            
            # Cargar archivos
            self.files = {}
            for path, data in snapshot.get("files", {}).items():
                self.files[path] = FileMetadata(
                    path=data["path"],
                    chunk_handles=data["chunk_handles"],
                    created_at=datetime.fromisoformat(data["created_at"])
                )
            
            # Cargar chunks
            self.chunks = {}
            for handle, data in snapshot.get("chunks", {}).items():
                self.chunks[handle] = ChunkMetadata(
                    handle=data["handle"],
                    replicas=[
                        ChunkLocation(
                            chunkserver_id=r["chunkserver_id"],
                            address=r["address"]
                        )
                        for r in data["replicas"]
                    ],
                    primary_id=data.get("primary_id"),
                    size=data.get("size", 0)
                )
            
            # Cargar chunkservers
            self.chunkservers = {}
            for cs_id, data in snapshot.get("chunkservers", {}).items():
                self.chunkservers[cs_id] = ChunkServerInfo(
                    id=data["id"],
                    address=data["address"],
                    chunks=data["chunks"],
                    last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]),
                    is_alive=data.get("is_alive", True)
                )
            
            # Reconstruir índice inverso
            self.chunkserver_chunks = defaultdict(set)
            for cs_id, cs_info in self.chunkservers.items():
                for chunk_handle in cs_info.chunks:
                    self.chunkserver_chunks[cs_id].add(chunk_handle)
            
            return True
        except Exception as e:
            print(f"Error cargando snapshot: {e}")
            return False

