"""
Tipos de datos compartidos para el mini-GFS.

Define las estructuras de datos principales que se usan entre
Master, ChunkServers y Client.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
import uuid


# Tipo alias para chunk handles (IDs únicos de chunks)
ChunkHandle = str


@dataclass
class ChunkLocation:
    """Ubicación de una réplica de un chunk en un ChunkServer específico"""
    chunkserver_id: str
    address: str  # e.g., "http://localhost:8001"


@dataclass
class ChunkMetadata:
    """
    Metadatos de un chunk.
    
    En GFS, el Master mantiene información sobre cada chunk:
    - Dónde están las réplicas (chunkservers)
    - Cuál es el primary (si hay lease activo)
    - Versión del chunk (se incrementa en cada mutación)
    """
    handle: ChunkHandle
    version: int = 0  # Versión del chunk (se incrementa en mutaciones)
    replicas: List[ChunkLocation] = field(default_factory=list)
    primary_id: Optional[str] = None  # ID del chunkserver que es primary
    size: int = 0  # Tamaño actual del chunk en bytes
    reference_count: int = 1  # Número de archivos que referencian este chunk (para snapshots)
    garbage_since: Optional[datetime] = None  # Timestamp cuando se marcó como garbage (None si no es garbage)


@dataclass
class FileMetadata:
    """
    Metadatos de un archivo.
    
    En GFS, los archivos se dividen en chunks de tamaño fijo.
    Este objeto mantiene la lista ordenada de chunk handles que
    componen el archivo.
    """
    path: str
    chunk_handles: List[ChunkHandle] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class LeaseInfo:
    """
    Información de un lease (arrendamiento) de un chunk.
    
    En GFS, el Master otorga leases a un chunkserver para que actúe
    como primary para un chunk. El primary coordina las mutaciones
    (writes/appends) entre las réplicas.
    """
    chunk_handle: ChunkHandle
    primary_id: str
    expiration: datetime


@dataclass
class ChunkServerInfo:
    """Información de un ChunkServer registrado en el Master"""
    id: str
    address: str
    rack_id: str = "default"  # ID del rack donde está ubicado el ChunkServer
    last_heartbeat: datetime = field(default_factory=datetime.now)
    chunks: List[ChunkHandle] = field(default_factory=list)
    is_alive: bool = True


# ========== Request/Response types para Master API ==========

@dataclass
class RegisterChunkServerRequest:
    """Request para registrar un ChunkServer"""
    chunkserver_id: str
    address: str
    chunks: List[ChunkHandle]


@dataclass
class RegisterChunkServerResponse:
    """Response del registro de ChunkServer"""
    success: bool
    message: str


@dataclass
class HeartbeatRequest:
    """Request de heartbeat de un ChunkServer"""
    chunkserver_id: str
    chunks: List[ChunkHandle]


@dataclass
class HeartbeatResponse:
    """Response del heartbeat"""
    success: bool
    message: str


@dataclass
class CreateFileRequest:
    """Request para crear un archivo"""
    path: str


@dataclass
class CreateFileResponse:
    """Response de creación de archivo"""
    success: bool
    message: str


@dataclass
class GetFileInfoRequest:
    """Request para obtener información de un archivo"""
    path: str


@dataclass
class GetFileInfoResponse:
    """Response con información del archivo"""
    success: bool
    path: str
    chunk_handles: List[ChunkHandle]
    chunks_info: List[Dict]  # Lista de dicts con info de cada chunk


@dataclass
class AllocateChunkRequest:
    """Request para asignar un nuevo chunk a un archivo"""
    path: str
    chunk_index: int  # Índice del chunk en la lista de chunks del archivo


@dataclass
class AllocateChunkResponse:
    """Response con el chunk handle y ubicaciones de réplicas"""
    success: bool
    chunk_handle: Optional[ChunkHandle] = None
    replicas: List[ChunkLocation] = field(default_factory=list)
    primary_id: Optional[str] = None


@dataclass
class GetChunkLocationsRequest:
    """Request para obtener ubicaciones de un chunk"""
    chunk_handle: ChunkHandle


@dataclass
class GetChunkLocationsResponse:
    """Response con ubicaciones del chunk"""
    success: bool
    chunk_handle: ChunkHandle
    replicas: List[ChunkLocation] = field(default_factory=list)
    primary_id: Optional[str] = None


# ========== Request/Response types para ChunkServer API ==========

@dataclass
class WriteChunkRequest:
    """Request para escribir datos en un chunk"""
    chunk_handle: ChunkHandle
    offset: int
    data: bytes  # En JSON se enviará como base64


@dataclass
class WriteChunkResponse:
    """Response de escritura"""
    success: bool
    message: str
    bytes_written: int = 0


@dataclass
class ReadChunkRequest:
    """Request para leer datos de un chunk"""
    chunk_handle: ChunkHandle
    offset: int
    length: int


@dataclass
class ReadChunkResponse:
    """Response de lectura"""
    success: bool
    data: bytes  # En JSON se enviará como base64
    bytes_read: int = 0


@dataclass
class AppendRecordRequest:
    """Request para append de un record"""
    chunk_handle: ChunkHandle
    data: bytes  # En JSON se enviará como base64


@dataclass
class AppendRecordResponse:
    """Response de append"""
    success: bool
    message: str
    offset: int = 0  # Offset donde se escribió el record
    bytes_written: int = 0


@dataclass
class CloneChunkRequest:
    """Request para clonar un chunk desde otro chunkserver"""
    chunk_handle: ChunkHandle
    src_address: str  # Dirección del chunkserver fuente


@dataclass
class CloneChunkResponse:
    """Response de clonación"""
    success: bool
    message: str

