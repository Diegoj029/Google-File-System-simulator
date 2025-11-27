"""
Carga de configuración desde archivos YAML.

Cada proceso (Master, ChunkServer) carga su configuración
desde archivos YAML en el directorio configs/.
"""
import yaml
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class MasterConfig:
    """Configuración del Master"""
    host: str = "localhost"
    port: int = 8000
    metadata_dir: str = "data/master"
    snapshot_file: str = "metadata_snapshot.json"
    chunk_size: int = 64 * 1024 * 1024  # 64 MB (como en GFS original)
    replication_factor: int = 3
    heartbeat_timeout: int = 30  # segundos
    lease_duration: int = 60  # segundos
    wal_dir: str = "data/master"  # Directorio para WAL
    wal_file: str = "wal.log"  # Nombre del archivo WAL


@dataclass
class ChunkServerConfig:
    """Configuración de un ChunkServer"""
    chunkserver_id: str = ""
    host: str = "localhost"
    port: int = 8001
    master_address: str = "http://localhost:8000"
    data_dir: str = "data/chunks"
    heartbeat_interval: int = 10  # segundos
    rack_id: str = "default"  # ID del rack donde está ubicado


def load_master_config(config_path: str = "configs/master.yaml") -> MasterConfig:
    """
    Carga la configuración del Master desde un archivo YAML.
    
    Si el archivo no existe, retorna valores por defecto.
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        # Retornar configuración por defecto
        return MasterConfig()
    
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f) or {}
    
    return MasterConfig(
        host=data.get("host", "localhost"),
        port=data.get("port", 8000),
        metadata_dir=data.get("metadata_dir", "data/master"),
        snapshot_file=data.get("snapshot_file", "metadata_snapshot.json"),
        chunk_size=data.get("chunk_size", 64 * 1024 * 1024),
        replication_factor=data.get("replication_factor", 3),
        heartbeat_timeout=data.get("heartbeat_timeout", 30),
        lease_duration=data.get("lease_duration", 60),
        wal_dir=data.get("wal_dir", data.get("metadata_dir", "data/master")),
        wal_file=data.get("wal_file", "wal.log")
    )


def load_chunkserver_config(config_path: str = "configs/chunkserver.yaml") -> ChunkServerConfig:
    """
    Carga la configuración de un ChunkServer desde un archivo YAML.
    
    Si el archivo no existe, retorna valores por defecto.
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        return ChunkServerConfig()
    
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f) or {}
    
    return ChunkServerConfig(
        chunkserver_id=data.get("chunkserver_id", ""),
        host=data.get("host", "localhost"),
        port=data.get("port", 8001),
        master_address=data.get("master_address", "http://localhost:8000"),
        data_dir=data.get("data_dir", "data/chunks"),
        heartbeat_interval=data.get("heartbeat_interval", 10),
        rack_id=data.get("rack_id", "default"),
        rack_id=data.get("rack_id", "default")
    )

