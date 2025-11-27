"""
Almacenamiento local de chunks en el ChunkServer.

Cada chunk se almacena como un archivo individual en disco.
Incluye verificación de integridad mediante checksums.
"""
import os
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict

from ..common.types import ChunkHandle


class ChecksumError(Exception):
    """Excepción lanzada cuando se detecta corrupción de datos"""
    pass


class ChunkStorage:
    """
    Gestor de almacenamiento de chunks en disco local.
    
    Cada chunk se guarda como un archivo: <data_dir>/<chunk_handle>.chunk
    Mantiene checksums de 32 bits para bloques de 64KB para verificación de integridad.
    """
    
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Checksums: chunk_handle -> {block_number: checksum}
        self.checksums: Dict[ChunkHandle, Dict[int, int]] = {}
        self.checksum_block_size = 64 * 1024  # 64 KB por bloque
        
        # Cargar checksums existentes
        self._load_checksums()
    
    def get_chunk_path(self, chunk_handle: ChunkHandle) -> Path:
        """Retorna la ruta del archivo para un chunk."""
        return self.data_dir / f"{chunk_handle}.chunk"
    
    def get_checksum_path(self, chunk_handle: ChunkHandle) -> Path:
        """Retorna la ruta del archivo de checksums para un chunk."""
        return self.data_dir / f"{chunk_handle}.checksums"
    
    def _calculate_checksum(self, data: bytes) -> int:
        """
        Calcula checksum de 32 bits para un bloque de datos.
        
        En GFS, se usa un checksum de 32 bits para cada bloque de 64KB.
        """
        # Usar MD5 y tomar los primeros 32 bits
        hash_value = hashlib.md5(data).digest()
        # Tomar los primeros 4 bytes y convertir a entero
        return int.from_bytes(hash_value[:4], byteorder='big') & 0xFFFFFFFF
    
    def _load_checksums(self):
        """Carga checksums desde disco."""
        for checksum_file in self.data_dir.glob("*.checksums"):
            chunk_handle = checksum_file.stem
            try:
                with open(checksum_file, 'r') as f:
                    self.checksums[chunk_handle] = json.load(f)
            except Exception as e:
                print(f"Error cargando checksums para {chunk_handle}: {e}")
                self.checksums[chunk_handle] = {}
    
    def _save_checksums(self, chunk_handle: ChunkHandle):
        """Guarda checksums de un chunk a disco."""
        if chunk_handle in self.checksums:
            checksum_path = self.get_checksum_path(chunk_handle)
            try:
                with open(checksum_path, 'w') as f:
                    json.dump(self.checksums[chunk_handle], f)
            except Exception as e:
                print(f"Error guardando checksums para {chunk_handle}: {e}")
    
    def _read_block(self, chunk_handle: ChunkHandle, block_number: int) -> Optional[bytes]:
        """Lee un bloque completo de un chunk."""
        chunk_path = self.get_chunk_path(chunk_handle)
        if not chunk_path.exists():
            return None
        
        block_offset = block_number * self.checksum_block_size
        with open(chunk_path, 'rb') as f:
            f.seek(block_offset)
            return f.read(self.checksum_block_size)
    
    def _update_checksums_for_range(self, chunk_handle: ChunkHandle, offset: int, length: int):
        """Actualiza checksums para los bloques afectados por una escritura."""
        if chunk_handle not in self.checksums:
            self.checksums[chunk_handle] = {}
        
        start_block = offset // self.checksum_block_size
        end_block = (offset + length - 1) // self.checksum_block_size
        
        for block_number in range(start_block, end_block + 1):
            block_data = self._read_block(chunk_handle, block_number)
            if block_data:
                self.checksums[chunk_handle][block_number] = self._calculate_checksum(block_data)
        
        self._save_checksums(chunk_handle)
    
    def _verify_checksums_for_range(self, chunk_handle: ChunkHandle, offset: int, length: int) -> bool:
        """Verifica checksums para los bloques leídos."""
        if chunk_handle not in self.checksums:
            # Si no hay checksums, asumir que está bien (chunk nuevo)
            return True
        
        start_block = offset // self.checksum_block_size
        end_block = (offset + length - 1) // self.checksum_block_size
        
        for block_number in range(start_block, end_block + 1):
            if block_number not in self.checksums[chunk_handle]:
                # Bloque sin checksum (puede ser nuevo)
                continue
            
            block_data = self._read_block(chunk_handle, block_number)
            if block_data:
                expected_checksum = self.checksums[chunk_handle][block_number]
                actual_checksum = self._calculate_checksum(block_data)
                if expected_checksum != actual_checksum:
                    return False
        
        return True
    
    def chunk_exists(self, chunk_handle: ChunkHandle) -> bool:
        """Verifica si un chunk existe en disco."""
        return self.get_chunk_path(chunk_handle).exists()
    
    def write_chunk(self, chunk_handle: ChunkHandle, offset: int, data: bytes) -> int:
        """
        Escribe datos en un chunk en la posición especificada.
        
        Args:
            chunk_handle: Handle del chunk
            offset: Offset dentro del chunk
            data: Datos a escribir
        
        Retorna:
            Número de bytes escritos
        """
        chunk_path = self.get_chunk_path(chunk_handle)
        
        # Leer chunk existente si existe
        existing_data = b''
        if chunk_path.exists():
            with open(chunk_path, 'rb') as f:
                existing_data = f.read()
        
        # Extender datos si es necesario
        total_size = max(len(existing_data), offset + len(data))
        new_data = bytearray(total_size)
        new_data[:len(existing_data)] = existing_data
        
        # Escribir nuevos datos
        new_data[offset:offset + len(data)] = data
        
        # Guardar
        with open(chunk_path, 'wb') as f:
            f.write(new_data)
        
        # Actualizar checksums de bloques afectados
        self._update_checksums_for_range(chunk_handle, offset, len(data))
        
        return len(data)
    
    def read_chunk(self, chunk_handle: ChunkHandle, offset: int, length: int, verify_checksum: bool = True) -> Optional[bytes]:
        """
        Lee datos de un chunk.
        
        Args:
            chunk_handle: Handle del chunk
            offset: Offset dentro del chunk
            length: Número de bytes a leer
            verify_checksum: Si True, verifica checksums antes de leer
        
        Retorna:
            Datos leídos, o None si el chunk no existe
        Lanza:
            ChecksumError si se detecta corrupción
        """
        chunk_path = self.get_chunk_path(chunk_handle)
        
        if not chunk_path.exists():
            return None
        
        # Verificar checksums antes de leer
        if verify_checksum:
            if not self._verify_checksums_for_range(chunk_handle, offset, length):
                raise ChecksumError(f"Corrupción detectada en chunk {chunk_handle} en offset {offset}")
        
        with open(chunk_path, 'rb') as f:
            f.seek(offset)
            data = f.read(length)
        
        return data
    
    def append_record(self, chunk_handle: ChunkHandle, data: bytes, chunk_size: int) -> tuple[int, int]:
        """
        Añade un record al final de un chunk.
        
        En GFS, record append es una operación atómica que:
        - Escribe el record en un offset determinado
        - Si no cabe, puede crear un nuevo chunk
        
        Args:
            chunk_handle: Handle del chunk
            data: Datos a añadir
            chunk_size: Tamaño máximo del chunk
        
        Retorna:
            (offset, bytes_written) donde se escribió el record
        """
        chunk_path = self.get_chunk_path(chunk_handle)
        
        # Obtener tamaño actual
        current_size = 0
        if chunk_path.exists():
            current_size = chunk_path.stat().st_size
        
        # Calcular offset donde escribir
        offset = current_size
        
        # Verificar si cabe en el chunk
        if offset + len(data) > chunk_size:
            # No cabe completamente, pero lo escribimos hasta donde sea posible
            # En GFS real, esto podría requerir padding y nuevo chunk
            available_space = chunk_size - offset
            if available_space > 0:
                data = data[:available_space]
            else:
                # Chunk lleno, retornar error (el cliente debería crear nuevo chunk)
                return (-1, 0)
        
        # Escribir
        bytes_written = self.write_chunk(chunk_handle, offset, data)
        return (offset, bytes_written)
    
    def delete_chunk(self, chunk_handle: ChunkHandle) -> bool:
        """Elimina un chunk y sus checksums."""
        chunk_path = self.get_chunk_path(chunk_handle)
        checksum_path = self.get_checksum_path(chunk_handle)
        
        try:
            if chunk_path.exists():
                chunk_path.unlink()
            if checksum_path.exists():
                checksum_path.unlink()
            if chunk_handle in self.checksums:
                del self.checksums[chunk_handle]
            return True
        except Exception as e:
            print(f"Error eliminando chunk {chunk_handle}: {e}")
            return False
    
    def get_chunk_size(self, chunk_handle: ChunkHandle) -> int:
        """Retorna el tamaño actual de un chunk."""
        chunk_path = self.get_chunk_path(chunk_handle)
        if chunk_path.exists():
            return chunk_path.stat().st_size
        return 0
    
    def list_chunks(self) -> list[ChunkHandle]:
        """
        Lista todos los chunks almacenados localmente.
        
        Retorna lista de chunk handles.
        """
        chunks = []
        for file_path in self.data_dir.glob("*.chunk"):
            # Extraer chunk handle del nombre del archivo
            chunk_handle = file_path.stem
            chunks.append(chunk_handle)
        return chunks
    
    def clone_chunk(self, chunk_handle: ChunkHandle, src_address: str) -> bool:
        """
        Clona un chunk desde otro ChunkServer.
        
        En GFS, cuando se necesita re-replicar, el Master instruye
        a un ChunkServer destino para que clone el chunk desde una fuente.
        
        Args:
            chunk_handle: Handle del chunk a clonar
            src_address: Dirección del ChunkServer fuente (e.g., "http://localhost:8001")
        
        Retorna:
            True si se clonó exitosamente, False en caso contrario
        """
        import requests
        
        try:
            # Leer chunk desde el ChunkServer fuente
            response = requests.post(
                f"{src_address}/read_chunk",
                json={
                    "chunk_handle": chunk_handle,
                    "offset": 0,
                    "length": 10 * 1024 * 1024  # Leer hasta 10MB (más que suficiente)
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return False
            
            result = response.json()
            if not result.get("success"):
                return False
            
            # Decodificar datos (vienen en base64)
            import base64
            chunk_data = base64.b64decode(result["data"])
            
            # Escribir chunk localmente
            self.write_chunk(chunk_handle, 0, chunk_data)
            
            return True
        except Exception as e:
            print(f"Error clonando chunk {chunk_handle} desde {src_address}: {e}")
            return False

