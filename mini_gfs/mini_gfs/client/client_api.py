"""
API del Cliente para comunicarse con Master y ChunkServers.

El cliente coordina operaciones entre el Master (para metadatos)
y los ChunkServers (para datos).
"""
import requests
import base64
import time
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
    
    def _record_operation(self, operation_type: str, start_time: float, end_time: float,
                         success: bool, bytes_transferred: int):
        """
        Registra una operación en el Master para métricas.
        
        Args:
            operation_type: Tipo de operación ('read', 'write', 'append')
            start_time: Timestamp de inicio
            end_time: Timestamp de fin
            success: Si la operación fue exitosa
            bytes_transferred: Bytes transferidos
        """
        try:
            requests.post(
                f"{self.master_address}/record_operation",
                json={
                    "operation_type": operation_type,
                    "start_time": start_time,
                    "end_time": end_time,
                    "success": success,
                    "bytes_transferred": bytes_transferred,
                    "chunkserver_id": None  # El cliente no tiene chunkserver_id
                },
                timeout=1  # Timeout corto para no bloquear
            )
        except Exception:
            # Ignorar errores silenciosamente para no afectar el rendimiento
            pass
    
    def write(self, path: str, offset: int, data: bytes) -> bool:
        """
        Escribe datos en un archivo.
        
        Implementa:
        1. Copy-on-write: Si el chunk está compartido (reference_count > 1), lo clona antes de escribir
        2. División en múltiples chunks: Si los datos exceden el tamaño del chunk (1MB), los divide
        3. Data pipeline: Cliente → Réplica1 → Réplica2 → Réplica3
        """
        start_time = time.time()
        chunk_size = self.config.chunk_size
        data_remaining = data
        current_offset = offset
        overall_success = True
        total_bytes_written = 0
        
        # Dividir datos en múltiples chunks si es necesario
        while len(data_remaining) > 0:
            # Calcular qué chunk contiene este offset
            chunk_index = current_offset // chunk_size
            offset_in_chunk = current_offset % chunk_size
            
            # Calcular cuántos bytes escribir en este chunk
            bytes_in_this_chunk = min(len(data_remaining), chunk_size - offset_in_chunk)
            chunk_data = data_remaining[:bytes_in_this_chunk]
            
            # Encontrar o crear el chunk
            chunk_handle, _ = self._find_chunk_for_offset(path, current_offset)
            
            locations = None
            old_chunk_handle = None
            
            if not chunk_handle:
                # Asignar nuevo chunk
                chunk_info = self.allocate_chunk(path, chunk_index)
                if not chunk_info:
                    print(f"Error: No se pudo asignar chunk para offset {current_offset}")
                    overall_success = False
                    break
                
                chunk_handle = chunk_info.get("chunk_handle")
                if not chunk_handle:
                    print(f"Error: No se obtuvo chunk_handle al asignar chunk")
                    overall_success = False
                    break
                
                locations = chunk_info
            else:
                # Obtener ubicaciones del chunk existente
                locations = self.get_chunk_locations(chunk_handle)
                if not locations:
                    print(f"Error: No se encontraron ubicaciones para chunk {chunk_handle}")
                    overall_success = False
                    break
                
                # Implementar copy-on-write si el chunk está compartido
                reference_count = locations.get("reference_count", 1)
                if reference_count > 1:
                    # El chunk está compartido, clonarlo antes de escribir
                    old_chunk_handle = chunk_handle
                    
                    try:
                        response = requests.post(
                            f"{self.master_address}/clone_shared_chunk",
                            json={
                                "path": path,
                                "chunk_index": chunk_index,
                                "old_chunk_handle": old_chunk_handle
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                chunk_handle = result.get("chunk_handle")
                                # Obtener las nuevas ubicaciones del chunk clonado
                                locations = self.get_chunk_locations(chunk_handle)
                                if not locations:
                                    print(f"Error: No se encontraron ubicaciones para chunk clonado {chunk_handle}")
                                    overall_success = False
                                    break
                            else:
                                print(f"Error: No se pudo clonar chunk compartido: {result.get('message')}")
                                overall_success = False
                                break
                        else:
                            print(f"Error: Master retornó código {response.status_code} al clonar chunk")
                            overall_success = False
                            break
                    except Exception as e:
                        print(f"Error clonando chunk compartido: {e}")
                        overall_success = False
                        break
            
            replicas = locations.get("replicas", [])
            primary_id = locations.get("primary_id")
            
            if not replicas or not primary_id:
                print(f"Error: No hay réplicas disponibles o primary no asignado")
                overall_success = False
                break
            
            # Encontrar primary
            primary_address = None
            for replica in replicas:
                if replica["chunkserver_id"] == primary_id:
                    primary_address = replica["address"]
                    break
            
            if not primary_address:
                print(f"Error: No se encontró dirección del primary")
                overall_success = False
                break
            
            # Data pipeline: Cliente → Réplica1 → Réplica2 → Réplica3
            data_b64 = base64.b64encode(chunk_data).decode('utf-8')
            
            # Ordenar réplicas: primary primero, luego otras
            primary_replica = None
            secondary_replicas = []
            for replica in replicas:
                if replica["chunkserver_id"] == primary_id:
                    primary_replica = replica
                else:
                    secondary_replicas.append(replica)
            
            replicas_ordered = [primary_replica] + secondary_replicas if primary_replica else secondary_replicas
            
            # Obtener tamaño actual del chunk
            current_chunk_size = locations.get("size", 0) if locations else 0
            
            # Enviar datos en pipeline
            write_success = False
            max_chunk_size = 0
            
            for i, replica in enumerate(replicas_ordered):
                try:
                    if i == 0:
                        # Primera réplica recibe del cliente
                        response = requests.post(
                            f"{replica['address']}/write_chunk",
                            json={
                                "chunk_handle": chunk_handle,
                                "offset": offset_in_chunk,
                                "data": data_b64
                            },
                            timeout=30
                        )
                    else:
                        # Réplicas siguientes reciben de la anterior (pipeline)
                        prev_replica = replicas_ordered[i-1]
                        response = requests.post(
                            f"{replica['address']}/write_chunk_pipeline",
                            json={
                                "chunk_handle": chunk_handle,
                                "offset": offset_in_chunk,
                                "data": data_b64,
                                "src_address": prev_replica['address']
                            },
                            timeout=30
                        )
                    
                    if response.status_code == 200:
                        result = response.json()
                        write_success = result.get("success", False)
                        chunk_size_reported = result.get("chunk_size", 0)
                        if chunk_size_reported > max_chunk_size:
                            max_chunk_size = chunk_size_reported
                    else:
                        write_success = False
                        print(f"Warning: Error en pipeline a réplica {replica['chunkserver_id']}")
                except Exception as e:
                    print(f"Warning: Error en pipeline a réplica {replica['chunkserver_id']}: {e}")
                    write_success = False
            
            # Actualizar tamaño del chunk en el Master
            if write_success:
                if max_chunk_size == 0:
                    max_chunk_size = max(current_chunk_size, offset_in_chunk + len(chunk_data))
                else:
                    max_chunk_size = max(max_chunk_size, offset_in_chunk + len(chunk_data))
                
                try:
                    response = requests.post(
                        f"{self.master_address}/update_chunk_size",
                        json={
                            "chunk_handle": chunk_handle,
                            "size": max_chunk_size
                        },
                        timeout=10
                    )
                    if response.status_code != 200:
                        print(f"Warning: No se pudo actualizar tamaño del chunk en Master")
                except Exception as e:
                    print(f"Warning: Error actualizando tamaño del chunk: {e}")
            else:
                overall_success = False
            
            # Continuar con el siguiente chunk
            data_remaining = data_remaining[bytes_in_this_chunk:]
            current_offset += bytes_in_this_chunk
            if write_success:
                total_bytes_written += len(chunk_data)
        
        end_time = time.time()
        self._record_operation('write', start_time, end_time, overall_success, total_bytes_written)
        return overall_success
    
    def read(self, path: str, offset: int, length: int) -> Optional[bytes]:
        """
        Lee datos de un archivo.
        
        En GFS, el cliente puede leer de cualquier réplica disponible.
        """
        start_time = time.time()
        # Encontrar chunk
        chunk_handle, offset_in_chunk = self._find_chunk_for_offset(path, offset)
        if not chunk_handle:
            print(f"Error: No se encontró chunk para offset {offset}")
            self._record_operation('read', start_time, time.time(), False, 0)
            return None
        
        # Obtener ubicaciones del chunk
        locations = self.get_chunk_locations(chunk_handle)
        if not locations:
            print(f"Error: No se encontraron ubicaciones para chunk {chunk_handle}")
            self._record_operation('read', start_time, time.time(), False, 0)
            return None
        
        replicas = locations.get("replicas", [])
        if not replicas:
            print(f"Error: No hay réplicas disponibles")
            self._record_operation('read', start_time, time.time(), False, 0)
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
                        data = base64.b64decode(data_b64)
                        end_time = time.time()
                        self._record_operation('read', start_time, end_time, True, len(data))
                        return data
            except Exception as e:
                print(f"Warning: Error leyendo de réplica {replica['chunkserver_id']}: {e}")
                continue
        
        print(f"Error: No se pudo leer de ninguna réplica")
        self._record_operation('read', start_time, time.time(), False, 0)
        return None
    
    def append(self, path: str, data: bytes) -> bool:
        """
        Añade un record al final de un archivo.
        
        En GFS, record append es una operación atómica que:
        1. Selecciona el último chunk (o crea uno nuevo)
        2. Añade el record en un offset determinado
        3. Si no cabe, puede crear un nuevo chunk
        """
        start_time = time.time()
        # Obtener información del archivo
        file_info = self.get_file_info(path)
        if not file_info:
            print(f"Error: Archivo {path} no existe")
            self._record_operation('append', start_time, time.time(), False, 0)
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
                                    bytes_written = result.get("bytes_written", len(data))
                                    end_time = time.time()
                                    self._record_operation('append', start_time, end_time, True, bytes_written)
                                    return True
                                # Si falla porque el chunk está lleno, crear nuevo chunk
                        except Exception as e:
                            print(f"Error en append: {e}")
        
        # Si no hay chunk o el último está lleno, crear uno nuevo
        chunk_info = self.allocate_chunk(path, chunk_index)
        if not chunk_info:
            print(f"Error: No se pudo asignar nuevo chunk")
            self._record_operation('append', start_time, time.time(), False, 0)
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
                success = result.get("success", False)
                bytes_written = result.get("bytes_written", len(data)) if success else 0
                end_time = time.time()
                self._record_operation('append', start_time, end_time, success, bytes_written)
                return success
            
            self._record_operation('append', start_time, time.time(), False, 0)
            return False
        except Exception as e:
            print(f"Error en append: {e}")
            self._record_operation('append', start_time, time.time(), False, 0)
            return False
    
    def snapshot_file(self, source_path: str, dest_path: str) -> bool:
        """Crea un snapshot de un archivo."""
        try:
            response = requests.post(
                f"{self.master_address}/snapshot_file",
                json={
                    "source_path": source_path,
                    "dest_path": dest_path
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            
            return False
        except Exception as e:
            print(f"Error creando snapshot: {e}")
            return False
    
    def rename_file(self, old_path: str, new_path: str) -> bool:
        """Renombra un archivo."""
        try:
            response = requests.post(
                f"{self.master_address}/rename_file",
                json={
                    "old_path": old_path,
                    "new_path": new_path
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            
            return False
        except Exception as e:
            print(f"Error renombrando archivo: {e}")
            return False
    
    def delete_file(self, path: str) -> bool:
        """Elimina un archivo."""
        try:
            response = requests.post(
                f"{self.master_address}/delete_file",
                json={"path": path},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False)
            
            return False
        except Exception as e:
            print(f"Error eliminando archivo: {e}")
            return False
    
    def list_directory(self, dir_path: str = "/") -> Optional[List[str]]:
        """Lista archivos en un directorio."""
        try:
            response = requests.post(
                f"{self.master_address}/list_directory",
                json={"dir_path": dir_path},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result.get("files", [])
            
            return None
        except Exception as e:
            print(f"Error listando directorio: {e}")
            return None

