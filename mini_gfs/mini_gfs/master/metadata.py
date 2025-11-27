"""
Gestión de metadatos del Master.

Mantiene en memoria:
- Namespace de archivos (file_path -> FileMetadata)
- Mapeo de chunks (chunk_handle -> ChunkMetadata)
- Información de ChunkServers
- Leases activos

También maneja la persistencia periódica a disco (JSON snapshot) y
Write-Ahead Log (WAL) para recuperación ante fallos.
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
from .wal import WAL, OperationType


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
        
        # Inicializar Write-Ahead Log (WAL)
        wal_dir = config.wal_dir if hasattr(config, 'wal_dir') else str(self.metadata_dir)
        wal_file = config.wal_file if hasattr(config, 'wal_file') else 'wal.log'
        self.wal = WAL(wal_dir, wal_file)
    
    def create_file(self, path: str) -> bool:
        """
        Crea un nuevo archivo en el namespace.
        
        Retorna True si se creó exitosamente, False si ya existe.
        """
        if path in self.files:
            return False
        
        self.files[path] = FileMetadata(path=path)
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.CREATE_FILE, {"path": path})
        
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
        
        # Seleccionar réplicas de racks diferentes (hasta replication_factor)
        num_replicas = min(self.config.replication_factor, len(available_chunkservers))
        if num_replicas == 0:
            return None
        
        replica_locations = []
        racks_used = set()
        
        # Primero intentar seleccionar de racks diferentes
        for cs_id in available_chunkservers:
            if len(replica_locations) >= num_replicas:
                break
            cs_info = self.chunkservers.get(cs_id)
            if cs_info and cs_info.is_alive:
                # Si no hay muchos racks, permitir réplicas en el mismo rack
                if cs_info.rack_id not in racks_used or len(racks_used) >= len(available_chunkservers):
                    replica_locations.append(ChunkLocation(
                        chunkserver_id=cs_id,
                        address=cs_info.address
                    ))
                    racks_used.add(cs_info.rack_id)
        
        # Si no hay suficientes réplicas, completar sin restricción de racks
        if len(replica_locations) < num_replicas:
            for cs_id in available_chunkservers:
                if len(replica_locations) >= num_replicas:
                    break
                cs_info = self.chunkservers.get(cs_id)
                if cs_info and cs_info.is_alive:
                    if not any(r.chunkserver_id == cs_id for r in replica_locations):
                        replica_locations.append(ChunkLocation(
                            chunkserver_id=cs_id,
                            address=cs_info.address
                        ))
        
        if not replica_locations:
            return None
        
        # Crear metadatos del chunk (versión inicial 0)
        chunk_meta = ChunkMetadata(
            handle=chunk_handle,
            version=0,  # Versión inicial
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
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.ALLOCATE_CHUNK, {
            "path": path,
            "chunk_index": chunk_index,
            "chunk_handle": chunk_handle,
            "replicas": [
                {"chunkserver_id": r.chunkserver_id, "address": r.address}
                for r in replica_locations
            ]
        })
        
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
            # Obtener rack_id del request si está disponible
            rack_id = getattr(self, '_last_rack_id', "default")
            cs_info = ChunkServerInfo(
                id=chunkserver_id,
                address=address,
                rack_id=rack_id,
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
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.REGISTER_CHUNKSERVER, {
            "chunkserver_id": chunkserver_id,
            "address": address,
            "chunks": chunks.copy()
        })
        
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
        
        # Incrementar versión del chunk al otorgar lease (para mutaciones)
        chunk_meta.version += 1
        
        # Crear nuevo lease
        lease = LeaseInfo(
            chunk_handle=chunk_handle,
            primary_id=primary_id,
            expiration=datetime.now() + timedelta(seconds=self.config.lease_duration)
        )
        self.leases[chunk_handle] = lease
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.INCREMENT_VERSION, {
            "chunk_handle": chunk_handle,
            "version": chunk_meta.version
        })
        self.wal.log_operation(OperationType.GRANT_LEASE, {
            "chunk_handle": chunk_handle,
            "primary_id": primary_id,
            "expiration": lease.expiration.isoformat()
        })
        
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
        
        Si existe un snapshot, lo carga y luego aplica las operaciones
        del WAL que ocurrieron después del snapshot (replay del log).
        
        Retorna True si se cargó exitosamente, False en caso contrario.
        """
        snapshot_loaded = False
        
        # Intentar cargar snapshot si existe
        if self.snapshot_path.exists():
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
                
                snapshot_loaded = True
            except Exception as e:
                print(f"Error cargando snapshot: {e}")
                # Si falla, empezar desde cero y usar solo el WAL
        
        # Replay del WAL para aplicar todas las operaciones
        # (o todas si no había snapshot, o solo las posteriores si había)
        self._replay_wal()
        
        return snapshot_loaded or len(self.files) > 0
    
    def _replay_wal(self):
        """
        Reproduce todas las operaciones del WAL.
        
        Esto permite recuperar el estado completo desde el log,
        incluso si no hay snapshot o si el snapshot está desactualizado.
        """
        def apply_operation(op_type: OperationType, data: dict, sequence: int):
            """Aplica una operación del WAL."""
            try:
                if op_type == OperationType.CREATE_FILE:
                    path = data["path"]
                    if path not in self.files:
                        self.files[path] = FileMetadata(path=path)
                
                elif op_type == OperationType.ALLOCATE_CHUNK:
                    path = data["path"]
                    chunk_index = data["chunk_index"]
                    chunk_handle = data["chunk_handle"]
                    
                    file_meta = self.files.get(path)
                    if file_meta:
                        # Asegurar que la lista es suficientemente larga
                        while len(file_meta.chunk_handles) <= chunk_index:
                            file_meta.chunk_handles.append(None)
                        file_meta.chunk_handles[chunk_index] = chunk_handle
                        
                        # Crear metadatos del chunk
                        replicas = [
                            ChunkLocation(
                                chunkserver_id=r["chunkserver_id"],
                                address=r["address"]
                            )
                            for r in data["replicas"]
                        ]
                        
                        chunk_meta = ChunkMetadata(
                            handle=chunk_handle,
                            version=data.get("version", 0),
                            replicas=replicas,
                            primary_id=replicas[0].chunkserver_id if replicas else None
                        )
                        self.chunks[chunk_handle] = chunk_meta
                        
                        # Actualizar índice inverso
                        for loc in replicas:
                            self.chunkserver_chunks[loc.chunkserver_id].add(chunk_handle)
                
                elif op_type == OperationType.REGISTER_CHUNKSERVER:
                    chunkserver_id = data["chunkserver_id"]
                    address = data["address"]
                    chunks = data["chunks"]
                    
                    if chunkserver_id not in self.chunkservers:
                        self.chunkservers[chunkserver_id] = ChunkServerInfo(
                            id=chunkserver_id,
                            address=address,
                            chunks=chunks.copy()
                        )
                    else:
                        cs_info = self.chunkservers[chunkserver_id]
                        cs_info.address = address
                        cs_info.chunks = chunks.copy()
                    
                    # Actualizar índice inverso
                    self.chunkserver_chunks[chunkserver_id] = set(chunks)
                
                elif op_type == OperationType.GRANT_LEASE:
                    chunk_handle = data["chunk_handle"]
                    primary_id = data["primary_id"]
                    expiration = datetime.fromisoformat(data["expiration"])
                    
                    chunk_meta = self.chunks.get(chunk_handle)
                    if chunk_meta:
                        chunk_meta.primary_id = primary_id
                    
                    lease = LeaseInfo(
                        chunk_handle=chunk_handle,
                        primary_id=primary_id,
                        expiration=expiration
                    )
                    self.leases[chunk_handle] = lease
                
                elif op_type == OperationType.UPDATE_CHUNK_SIZE:
                    chunk_handle = data["chunk_handle"]
                    size = data["size"]
                    
                    chunk_meta = self.chunks.get(chunk_handle)
                    if chunk_meta:
                        chunk_meta.size = size
                
                elif op_type == OperationType.INCREMENT_VERSION:
                    chunk_handle = data["chunk_handle"]
                    version = data["version"]
                    
                    chunk_meta = self.chunks.get(chunk_handle)
                    if chunk_meta:
                        chunk_meta.version = version
                
                elif op_type == OperationType.SNAPSHOT_FILE:
                    source_path = data["source_path"]
                    dest_path = data["dest_path"]
                    
                    source_file = self.files.get(source_path)
                    if source_file:
                        dest_file = FileMetadata(path=dest_path)
                        dest_file.chunk_handles = source_file.chunk_handles.copy()
                        self.files[dest_path] = dest_file
                        
                        # Incrementar reference_count
                        for chunk_handle in dest_file.chunk_handles:
                            if chunk_handle:
                                chunk_meta = self.chunks.get(chunk_handle)
                                if chunk_meta:
                                    chunk_meta.reference_count += 1
                
                elif op_type == OperationType.RENAME_FILE:
                    old_path = data["old_path"]
                    new_path = data["new_path"]
                    
                    if old_path in self.files:
                        file_meta = self.files.pop(old_path)
                        file_meta.path = new_path
                        self.files[new_path] = file_meta
                
                elif op_type == OperationType.DELETE_FILE:
                    path = data["path"]
                    
                    if path in self.files:
                        file_meta = self.files.pop(path)
                        # Decrementar reference_count
                        for chunk_handle in file_meta.chunk_handles:
                            if chunk_handle:
                                chunk_meta = self.chunks.get(chunk_handle)
                                if chunk_meta:
                                    chunk_meta.reference_count -= 1
                                    if chunk_meta.reference_count <= 0:
                                        chunk_meta.garbage_since = datetime.now()
                
                elif op_type == OperationType.MARK_GARBAGE:
                    chunk_handle = data["chunk_handle"]
                    timestamp = datetime.fromisoformat(data["timestamp"])
                    
                    chunk_meta = self.chunks.get(chunk_handle)
                    if chunk_meta:
                        chunk_meta.garbage_since = timestamp
                
                elif op_type == OperationType.DELETE_CHUNK:
                    chunk_handle = data["chunk_handle"]
                    
                    if chunk_handle in self.chunks:
                        chunk_meta = self.chunks[chunk_handle]
                        # Remover de índice inverso
                        for replica in chunk_meta.replicas:
                            if chunk_handle in self.chunkserver_chunks.get(replica.chunkserver_id, set()):
                                self.chunkserver_chunks[replica.chunkserver_id].remove(chunk_handle)
                        del self.chunks[chunk_handle]
                        if chunk_handle in self.leases:
                            del self.leases[chunk_handle]
            
            except Exception as e:
                print(f"Error aplicando operación {op_type} del WAL: {e}")
        
        # Reproducir todas las operaciones del log
        count = self.wal.replay_log(apply_operation)
        if count > 0:
            print(f"Replay del WAL: {count} operaciones aplicadas")
    
    def update_chunk_size(self, chunk_handle: ChunkHandle, size: int):
        """
        Actualiza el tamaño de un chunk.
        
        Útil cuando se escribe en un chunk y se necesita actualizar
        el tamaño registrado en los metadatos.
        """
        chunk_meta = self.chunks.get(chunk_handle)
        if chunk_meta:
            # Solo actualizar si el nuevo tamaño es mayor (para evitar reducir el tamaño)
            if size > chunk_meta.size:
                chunk_meta.size = size
                
                # Registrar en WAL
                self.wal.log_operation(OperationType.UPDATE_CHUNK_SIZE, {
                    "chunk_handle": chunk_handle,
                    "size": size
                })
        else:
            # Si el chunk no existe en metadatos, no podemos actualizarlo
            # Esto no debería pasar en condiciones normales
            print(f"Warning: Intento de actualizar tamaño de chunk inexistente: {chunk_handle}")
    
    def snapshot_file(self, source_path: str, dest_path: str) -> bool:
        """
        Crea un snapshot (copia) de un archivo usando copy-on-write.
        
        En GFS, los snapshots son instantáneos porque los chunks se comparten
        hasta que se modifiquen (copy-on-write).
        
        Args:
            source_path: Ruta del archivo fuente
            dest_path: Ruta del archivo destino (snapshot)
        
        Retorna:
            True si se creó exitosamente, False en caso contrario
        """
        source_file = self.files.get(source_path)
        if not source_file:
            return False
        
        if dest_path in self.files:
            return False  # El destino ya existe
        
        # Crear nuevo archivo que referencia los mismos chunks (copy-on-write)
        dest_file = FileMetadata(path=dest_path)
        dest_file.chunk_handles = source_file.chunk_handles.copy()  # Compartir chunks
        
        self.files[dest_path] = dest_file
        
        # Incrementar reference_count de cada chunk compartido
        for chunk_handle in dest_file.chunk_handles:
            if chunk_handle:
                chunk_meta = self.chunks.get(chunk_handle)
                if chunk_meta:
                    chunk_meta.reference_count += 1
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.SNAPSHOT_FILE, {
            "source_path": source_path,
            "dest_path": dest_path
        })
        
        return True
    
    def rename_file(self, old_path: str, new_path: str) -> bool:
        """
        Renombra un archivo.
        
        Args:
            old_path: Ruta antigua
            new_path: Ruta nueva
        
        Retorna:
            True si se renombró exitosamente, False en caso contrario
        """
        if old_path not in self.files:
            return False
        
        if new_path in self.files:
            return False  # El destino ya existe
        
        file_meta = self.files.pop(old_path)
        file_meta.path = new_path
        self.files[new_path] = file_meta
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.RENAME_FILE, {
            "old_path": old_path,
            "new_path": new_path
        })
        
        return True
    
    def delete_file(self, path: str) -> bool:
        """
        Elimina un archivo.
        
        Los chunks se marcarán como garbage en el próximo garbage collection
        si no son referenciados por otros archivos (snapshots).
        
        Args:
            path: Ruta del archivo a eliminar
        
        Retorna:
            True si se eliminó exitosamente, False en caso contrario
        """
        if path not in self.files:
            return False
        
        file_meta = self.files.pop(path)
        
        # Decrementar reference_count de chunks
        for chunk_handle in file_meta.chunk_handles:
            if chunk_handle:
                chunk_meta = self.chunks.get(chunk_handle)
                if chunk_meta:
                    chunk_meta.reference_count -= 1
                    # Si reference_count llega a 0, marcar para garbage collection
                    if chunk_meta.reference_count <= 0:
                        chunk_meta.garbage_since = datetime.now()
                        self.wal.log_operation(OperationType.MARK_GARBAGE, {
                            "chunk_handle": chunk_handle,
                            "timestamp": chunk_meta.garbage_since.isoformat()
                        })
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.DELETE_FILE, {"path": path})
        
        return True
    
    def clone_shared_chunk(self, path: str, chunk_index: int, old_chunk_handle: ChunkHandle,
                          available_chunkservers: List[str]) -> Optional[ChunkHandle]:
        """
        Clona un chunk compartido (copy-on-write).
        
        Cuando se va a escribir en un chunk que está compartido (reference_count > 1),
        se debe clonar el chunk para que solo este archivo lo modifique.
        
        Args:
            path: Ruta del archivo que necesita el chunk clonado
            chunk_index: Índice del chunk en la lista de chunks del archivo
            old_chunk_handle: Handle del chunk original a clonar
            available_chunkservers: Lista de IDs de chunkservers disponibles
        
        Retorna:
            Nuevo chunk_handle del chunk clonado, o None si falla
        """
        file_meta = self.files.get(path)
        if not file_meta:
            return None
        
        old_chunk_meta = self.chunks.get(old_chunk_handle)
        if not old_chunk_meta:
            return None
        
        # Verificar que el chunk_index corresponde al old_chunk_handle
        if chunk_index >= len(file_meta.chunk_handles) or file_meta.chunk_handles[chunk_index] != old_chunk_handle:
            return None
        
        # Crear nuevo chunk con las mismas réplicas (se clonará el contenido después)
        new_chunk_handle = str(uuid.uuid4())
        
        # Usar las mismas réplicas que el chunk original
        replica_locations = []
        for old_replica in old_chunk_meta.replicas:
            if old_replica.chunkserver_id in available_chunkservers:
                cs_info = self.chunkservers.get(old_replica.chunkserver_id)
                if cs_info and cs_info.is_alive:
                    replica_locations.append(ChunkLocation(
                        chunkserver_id=old_replica.chunkserver_id,
                        address=old_replica.address
                    ))
        
        if not replica_locations:
            return None
        
        # Crear metadatos del nuevo chunk
        new_chunk_meta = ChunkMetadata(
            handle=new_chunk_handle,
            version=old_chunk_meta.version,  # Mantener la misma versión
            replicas=replica_locations,
            primary_id=old_chunk_meta.primary_id,  # Usar el mismo primary
            size=old_chunk_meta.size,  # Mantener el mismo tamaño inicial
            reference_count=1  # Nuevo chunk solo referenciado por este archivo
        )
        
        self.chunks[new_chunk_handle] = new_chunk_meta
        
        # Reemplazar el chunk handle en el archivo
        file_meta.chunk_handles[chunk_index] = new_chunk_handle
        
        # Decrementar reference_count del chunk original
        old_chunk_meta.reference_count -= 1
        
        # Actualizar índice inverso para el nuevo chunk
        for loc in replica_locations:
            self.chunkserver_chunks[loc.chunkserver_id].add(new_chunk_handle)
        
        # Registrar en WAL
        self.wal.log_operation(OperationType.ALLOCATE_CHUNK, {
            "path": path,
            "chunk_index": chunk_index,
            "chunk_handle": new_chunk_handle,
            "old_chunk_handle": old_chunk_handle,
            "replicas": [
                {"chunkserver_id": r.chunkserver_id, "address": r.address}
                for r in replica_locations
            ]
        })
        
        return new_chunk_handle
    
    def list_directory(self, dir_path: str = "/") -> List[str]:
        """
        Lista archivos en un directorio.
        
        Args:
            dir_path: Ruta del directorio (termina en /)
        
        Retorna:
            Lista de rutas de archivos en el directorio
        """
        if not dir_path.endswith('/'):
            dir_path += '/'
        
        if dir_path == '/':
            # Listar todos los archivos en la raíz
            return [path for path in self.files.keys() if '/' not in path[1:] or path.count('/') == 1]
        else:
            # Listar archivos en el directorio especificado
            prefix = dir_path
            return [path for path in self.files.keys() if path.startswith(prefix)]
    
    def garbage_collect_chunks(self) -> List[ChunkHandle]:
        """
        Identifica chunks huérfanos (no referenciados por ningún archivo).
        
        Retorna:
            Lista de chunk handles marcados como garbage
        """
        # Obtener todos los chunks referenciados
        referenced_chunks = set()
        for file_meta in self.files.values():
            for chunk_handle in file_meta.chunk_handles:
                if chunk_handle:
                    referenced_chunks.add(chunk_handle)
        
        # Encontrar chunks no referenciados
        all_chunks = set(self.chunks.keys())
        orphaned_chunks = all_chunks - referenced_chunks
        
        # Marcar para eliminación (con timestamp)
        newly_marked = []
        for chunk_handle in orphaned_chunks:
            chunk_meta = self.chunks.get(chunk_handle)
            if chunk_meta and not chunk_meta.garbage_since:
                chunk_meta.garbage_since = datetime.now()
                newly_marked.append(chunk_handle)
                self.wal.log_operation(OperationType.MARK_GARBAGE, {
                    "chunk_handle": chunk_handle,
                    "timestamp": chunk_meta.garbage_since.isoformat()
                })
        
        return newly_marked
    
    def get_garbage_chunks_to_delete(self, garbage_retention_days: int = 3) -> List[ChunkHandle]:
        """
        Retorna chunks marcados como garbage que pueden ser eliminados
        (han estado marcados por más de garbage_retention_days días).
        
        Args:
            garbage_retention_days: Días de retención antes de eliminar
        
        Retorna:
            Lista de chunk handles que pueden ser eliminados
        """
        cutoff = datetime.now() - timedelta(days=garbage_retention_days)
        to_delete = []
        
        for chunk_handle, chunk_meta in self.chunks.items():
            if chunk_meta.garbage_since and chunk_meta.garbage_since < cutoff:
                to_delete.append(chunk_handle)
        
        return to_delete
    
    def delete_chunk(self, chunk_handle: ChunkHandle) -> bool:
        """
        Elimina un chunk de los metadatos.
        
        Nota: Esto solo elimina de los metadatos. Los ChunkServers
        deben eliminar los datos físicos.
        
        Args:
            chunk_handle: Handle del chunk a eliminar
        
        Retorna:
            True si se eliminó exitosamente
        """
        if chunk_handle in self.chunks:
            chunk_meta = self.chunks[chunk_handle]
            
            # Remover de índice inverso
            for replica in chunk_meta.replicas:
                if chunk_handle in self.chunkserver_chunks.get(replica.chunkserver_id, set()):
                    self.chunkserver_chunks[replica.chunkserver_id].remove(chunk_handle)
            
            # Eliminar chunk
            del self.chunks[chunk_handle]
            
            # Eliminar lease si existe
            if chunk_handle in self.leases:
                del self.leases[chunk_handle]
            
            # Registrar en WAL
            self.wal.log_operation(OperationType.DELETE_CHUNK, {
                "chunk_handle": chunk_handle
            })
            
            return True
        
        return False

