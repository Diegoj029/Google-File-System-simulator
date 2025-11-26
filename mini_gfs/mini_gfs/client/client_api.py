"""
API del Cliente para comunicarse con Master y ChunkServers.

El cliente coordina operaciones entre el Master (para metadatos)
y los ChunkServers (para datos).
"""
import requests
import base64
from typing import Optional, List, Dict

from ..common.types import ChunkHandle, ChunkLocation
from ..common.config import MasterConfig, load_master_config


class ClientAPI:
    """
    Cliente para interactuar con el mini-GFS.
    
    Similar al cliente en GFS, coordina operaciones entre
    Master (metadatos) y ChunkServers (datos).
    """
    
    def __init__(self, master_address: str = "http://localhost:8000"):
        self.master_address = master_address
        self.config = load_master_config()
    
    def create_file(self, path: str) -> bool:
        """Crea un nuevo archivo."""
        try:
            response = requests.post(
                f"{self.master_address}/create_file",
                json={"path": path},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            return False
        except Exception as e:
            print(f"Error creando archivo: {e}")
            return False
    
    def get_file_info(self, path: str) -> Optional[Dict]:
        """Obtiene información de un archivo."""
        try:
            response = requests.post(
                f"{self.master_address}/get_file_info",
                json={"path": path},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result
            return None
        except Exception as e:
            print(f"Error obteniendo información de archivo: {e}")
            return None
    
    def allocate_chunk(self, path: str, chunk_index: int) -> Optional[Dict]:
        """Solicita asignación de un nuevo chunk."""
        try:
            response = requests.post(
                f"{self.master_address}/allocate_chunk",
                json={
                    "path": path,
                    "chunk_index": chunk_index
                },
                timeout=30  # Aumentar timeout a 30 segundos
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result
            else:
                print(f"Error: Master retornó código {response.status_code}: {response.text}")
            return None
        except requests.exceptions.Timeout:
            print(f"Error: Timeout al comunicarse con Master en {self.master_address}")
            print("Verifica que el Master esté corriendo y no esté bloqueado")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"Error: No se pudo conectar con Master en {self.master_address}")
            print(f"Detalles: {e}")
            return None
        except Exception as e:
            print(f"Error asignando chunk: {e}")
            return None
    
    def get_chunk_locations(self, chunk_handle: ChunkHandle) -> Optional[Dict]:
        """Obtiene ubicaciones de un chunk."""
        try:
            response = requests.post(
                f"{self.master_address}/get_chunk_locations",
                json={"chunk_handle": chunk_handle},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result
            return None
        except Exception as e:
            print(f"Error obteniendo ubicaciones de chunk: {e}")
            return None
    
    def _find_chunk_for_offset(self, path: str, offset: int) -> tuple[Optional[ChunkHandle], int]:
        """
        Encuentra el chunk que contiene un offset dado.
        
        Retorna (chunk_handle, offset_in_chunk) o (None, 0) si no se encuentra.
        """
        file_info = self.get_file_info(path)
        if not file_info:
            return (None, 0)
        
        chunk_handles = file_info.get("chunk_handles", [])
        chunk_size = self.config.chunk_size
        
        # Calcular qué chunk contiene el offset
        chunk_index = offset // chunk_size
        offset_in_chunk = offset % chunk_size
        
        if chunk_index >= len(chunk_handles) or not chunk_handles[chunk_index]:
            return (None, 0)
        
        return (chunk_handles[chunk_index], offset_in_chunk)
    
    def write(self, path: str, offset: int, data: bytes) -> bool:
        """
        Escribe datos en un archivo.
        
        En GFS, el cliente:
        1. Obtiene ubicaciones del chunk del Master
        2. Envía datos a todas las réplicas (data push)
        3. Instruye al primary para coordinar la escritura
        """
        # Encontrar chunk
        chunk_handle, offset_in_chunk = self._find_chunk_for_offset(path, offset)
        
        # Si no existe el chunk, asignarlo
        locations = None
        if not chunk_handle:
            # Calcular qué chunk_index necesitamos
            chunk_size = self.config.chunk_size
            chunk_index = offset // chunk_size
            
            # Asignar el chunk
            chunk_info = self.allocate_chunk(path, chunk_index)
            if not chunk_info:
                print(f"Error: No se pudo asignar chunk para offset {offset}")
                return False
            
            chunk_handle = chunk_info.get("chunk_handle")
            if not chunk_handle:
                print(f"Error: No se obtuvo chunk_handle al asignar chunk")
                return False
            
            # Usar la información del chunk recién asignado
            locations = chunk_info
            # Recalcular offset_in_chunk
            offset_in_chunk = offset % chunk_size
        else:
            # Obtener ubicaciones del chunk existente
            locations = self.get_chunk_locations(chunk_handle)
        
        if not locations:
            print(f"Error: No se encontraron ubicaciones para chunk {chunk_handle}")
            return False
        
        replicas = locations.get("replicas", [])
        primary_id = locations.get("primary_id")
        
        if not replicas or not primary_id:
            print(f"Error: No hay réplicas disponibles o primary no asignado")
            return False
        
        # Encontrar primary
        primary_address = None
        for replica in replicas:
            if replica["chunkserver_id"] == primary_id:
                primary_address = replica["address"]
                break
        
        if not primary_address:
            print(f"Error: No se encontró dirección del primary")
            return False
        
        # Enviar datos a todas las réplicas (data push)
        data_b64 = base64.b64encode(data).decode('utf-8')
        
        # Primero enviar datos a todas las réplicas
        for replica in replicas:
            try:
                response = requests.post(
                    f"{replica['address']}/write_chunk",
                    json={
                        "chunk_handle": chunk_handle,
                        "offset": offset_in_chunk,
                        "data": data_b64
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    print(f"Warning: Error enviando datos a réplica {replica['chunkserver_id']}")
            except Exception as e:
                print(f"Warning: Error enviando datos a réplica {replica['chunkserver_id']}: {e}")
        
        # El primary coordina la escritura (en GFS real, el primary aplica en orden
        # y replica a secondaries, pero aquí simplificamos)
        try:
            response = requests.post(
                f"{primary_address}/write_chunk",
                json={
                    "chunk_handle": chunk_handle,
                    "offset": offset_in_chunk,
                    "data": data_b64
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            
            return False
        except Exception as e:
            print(f"Error escribiendo en primary: {e}")
            return False
    
    def read(self, path: str, offset: int, length: int) -> Optional[bytes]:
        """
        Lee datos de un archivo.
        
        En GFS, el cliente puede leer de cualquier réplica disponible.
        """
        # Encontrar chunk
        chunk_handle, offset_in_chunk = self._find_chunk_for_offset(path, offset)
        if not chunk_handle:
            print(f"Error: No se encontró chunk para offset {offset}")
            return None
        
        # Obtener ubicaciones del chunk
        locations = self.get_chunk_locations(chunk_handle)
        if not locations:
            print(f"Error: No se encontraron ubicaciones para chunk {chunk_handle}")
            return None
        
        replicas = locations.get("replicas", [])
        if not replicas:
            print(f"Error: No hay réplicas disponibles")
            return None
        
        # Intentar leer de la primera réplica disponible
        for replica in replicas:
            try:
                response = requests.post(
                    f"{replica['address']}/read_chunk",
                    json={
                        "chunk_handle": chunk_handle,
                        "offset": offset_in_chunk,
                        "length": length
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        data_b64 = result.get("data")
                        return base64.b64decode(data_b64)
            except Exception as e:
                print(f"Warning: Error leyendo de réplica {replica['chunkserver_id']}: {e}")
                continue
        
        print(f"Error: No se pudo leer de ninguna réplica")
        return None
    
    def append(self, path: str, data: bytes) -> bool:
        """
        Añade un record al final de un archivo.
        
        En GFS, record append es una operación atómica que:
        1. Selecciona el último chunk (o crea uno nuevo)
        2. Añade el record en un offset determinado
        3. Si no cabe, puede crear un nuevo chunk
        """
        # Obtener información del archivo
        file_info = self.get_file_info(path)
        if not file_info:
            print(f"Error: Archivo {path} no existe")
            return False
        
        chunk_handles = file_info.get("chunk_handles", [])
        chunk_size = self.config.chunk_size
        
        # Encontrar el último chunk o crear uno nuevo
        chunk_handle = None
        chunk_index = len(chunk_handles)
        
        if chunk_handles and chunk_handles[-1]:
            # Intentar usar el último chunk
            chunk_handle = chunk_handles[-1]
            
            # Obtener ubicaciones
            locations = self.get_chunk_locations(chunk_handle)
            if locations:
                replicas = locations.get("replicas", [])
                primary_id = locations.get("primary_id")
                
                if replicas and primary_id:
                    # Encontrar primary
                    primary_address = None
                    for replica in replicas:
                        if replica["chunkserver_id"] == primary_id:
                            primary_address = replica["address"]
                            break
                    
                    if primary_address:
                        # Intentar append en el último chunk
                        data_b64 = base64.b64encode(data).decode('utf-8')
                        
                        try:
                            response = requests.post(
                                f"{primary_address}/append_record",
                                json={
                                    "chunk_handle": chunk_handle,
                                    "data": data_b64
                                },
                                timeout=30
                            )
                            
                            if response.status_code == 200:
                                result = response.json()
                                if result.get("success"):
                                    return True
                                # Si falla porque el chunk está lleno, crear nuevo chunk
                        except Exception as e:
                            print(f"Error en append: {e}")
        
        # Si no hay chunk o el último está lleno, crear uno nuevo
        chunk_info = self.allocate_chunk(path, chunk_index)
        if not chunk_info:
            print(f"Error: No se pudo asignar nuevo chunk")
            return False
        
        chunk_handle = chunk_info.get("chunk_handle")
        replicas = chunk_info.get("replicas", [])
        primary_id = chunk_info.get("primary_id")
        
        if not chunk_handle or not replicas or not primary_id:
            print(f"Error: Información de chunk incompleta")
            return False
        
        # Encontrar primary
        primary_address = None
        for replica in replicas:
            if replica["chunkserver_id"] == primary_id:
                primary_address = replica["address"]
                break
        
        if not primary_address:
            print(f"Error: No se encontró dirección del primary")
            return False
        
        # Hacer append en el nuevo chunk
        data_b64 = base64.b64encode(data).decode('utf-8')
        
        try:
            response = requests.post(
                f"{primary_address}/append_record",
                json={
                    "chunk_handle": chunk_handle,
                    "data": data_b64
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            
            return False
        except Exception as e:
            print(f"Error en append: {e}")
            return False

