"""
Write-Ahead Log (WAL) para el Master.

En GFS, el Master mantiene un log de todas las operaciones de mutación
antes de aplicarlas a los metadatos en memoria. Esto permite:
- Recuperación ante fallos
- Replicación del Master (no implementado aquí)
- Consistencia de datos

El WAL registra operaciones como:
- CREATE_FILE
- ALLOCATE_CHUNK
- REGISTER_CHUNKSERVER
- UPDATE_CHUNK_SIZE
- GRANT_LEASE
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class OperationType(Enum):
    """Tipos de operaciones que se registran en el WAL"""
    CREATE_FILE = "CREATE_FILE"
    ALLOCATE_CHUNK = "ALLOCATE_CHUNK"
    REGISTER_CHUNKSERVER = "REGISTER_CHUNKSERVER"
    UPDATE_CHUNK_SIZE = "UPDATE_CHUNK_SIZE"
    GRANT_LEASE = "GRANT_LEASE"
    UPDATE_REPLICAS = "UPDATE_REPLICAS"
    DELETE_CHUNK = "DELETE_CHUNK"
    INCREMENT_VERSION = "INCREMENT_VERSION"
    SNAPSHOT_FILE = "SNAPSHOT_FILE"
    RENAME_FILE = "RENAME_FILE"
    DELETE_FILE = "DELETE_FILE"
    MARK_GARBAGE = "MARK_GARBAGE"


class WAL:
    """
    Write-Ahead Log para el Master.
    
    Registra todas las operaciones de mutación en un archivo de log
    antes de aplicarlas a los metadatos en memoria. Similar al WAL
    en bases de datos y sistemas de archivos distribuidos.
    """
    
    def __init__(self, log_dir: str, log_file: str = "wal.log"):
        """
        Inicializa el WAL.
        
        Args:
            log_dir: Directorio donde se guardan los logs
            log_file: Nombre del archivo de log
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / log_file
        self.log_file_handle = None
        self._sequence_number = 0
        
        # Cargar el último sequence number si el log existe
        self._load_last_sequence()
    
    def _load_last_sequence(self):
        """Carga el último sequence number desde el log existente."""
        if not self.log_path.exists():
            self._sequence_number = 0
            return
        
        try:
            # Leer el último entry para obtener el sequence number
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
                if lines:
                    # Buscar el último entry válido
                    for line in reversed(lines):
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                self._sequence_number = entry.get("sequence", 0)
                                break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            print(f"Error cargando último sequence number: {e}")
            self._sequence_number = 0
    
    def _open_log(self):
        """Abre el archivo de log en modo append."""
        if self.log_file_handle is None:
            self.log_file_handle = open(self.log_path, 'a')
    
    def _close_log(self):
        """Cierra el archivo de log."""
        if self.log_file_handle:
            self.log_file_handle.close()
            self.log_file_handle = None
    
    def log_operation(self, operation_type: OperationType, data: Dict[str, Any]) -> int:
        """
        Registra una operación en el WAL.
        
        Args:
            operation_type: Tipo de operación
            data: Datos de la operación (debe ser serializable a JSON)
        
        Returns:
            Sequence number de la operación registrada
        """
        self._open_log()
        
        self._sequence_number += 1
        entry = {
            "sequence": self._sequence_number,
            "timestamp": datetime.now().isoformat(),
            "operation": operation_type.value,
            "data": data
        }
        
        # Escribir como línea JSON (formato append-only)
        log_line = json.dumps(entry) + "\n"
        self.log_file_handle.write(log_line)
        self.log_file_handle.flush()  # Asegurar que se escribe inmediatamente
        os.fsync(self.log_file_handle.fileno())  # Forzar escritura a disco
        
        return self._sequence_number
    
    def replay_log(self, callback: callable) -> int:
        """
        Reproduce todas las operaciones del log.
        
        Útil para recuperación después de un fallo. Lee todas las
        entradas del log y las aplica usando el callback proporcionado.
        
        Args:
            callback: Función que recibe (operation_type, data, sequence) y aplica la operación
        
        Returns:
            Número de operaciones reproducidas
        """
        if not self.log_path.exists():
            return 0
        
        count = 0
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                        operation_type = OperationType(entry["operation"])
                        data = entry["data"]
                        sequence = entry.get("sequence", 0)
                        
                        callback(operation_type, data, sequence)
                        count += 1
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        print(f"Error procesando entrada del log: {e}")
                        continue
        
        except Exception as e:
            print(f"Error leyendo log para replay: {e}")
        
        return count
    
    def get_last_sequence(self) -> int:
        """Retorna el último sequence number."""
        return self._sequence_number
    
    def checkpoint(self, checkpoint_path: Path):
        """
        Crea un checkpoint del log.
        
        En GFS real, los checkpoints permiten truncar el log después
        de un punto conocido. Aquí simplificamos guardando el log completo
        pero marcando un punto de checkpoint.
        
        Args:
            checkpoint_path: Ruta donde guardar el checkpoint
        """
        checkpoint_data = {
            "checkpoint_time": datetime.now().isoformat(),
            "last_sequence": self._sequence_number,
            "log_file": str(self.log_path)
        }
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
    
    def truncate_after_checkpoint(self, checkpoint_sequence: int):
        """
        Trunca el log después de un checkpoint.
        
        En producción, esto se haría de forma más sofisticada.
        Aquí simplificamos creando un nuevo archivo con las entradas
        después del checkpoint.
        
        Args:
            checkpoint_sequence: Sequence number del checkpoint
        """
        if not self.log_path.exists():
            return
        
        # Leer todas las entradas después del checkpoint
        new_entries = []
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                        if entry.get("sequence", 0) > checkpoint_sequence:
                            new_entries.append(line)
                    except json.JSONDecodeError:
                        continue
            
            # Reescribir el log solo con las entradas después del checkpoint
            if new_entries:
                with open(self.log_path, 'w') as f:
                    for entry_line in new_entries:
                        f.write(entry_line + "\n")
            else:
                # Si no hay entradas nuevas, truncar el archivo
                self.log_path.unlink()
                self._sequence_number = checkpoint_sequence
        
        except Exception as e:
            print(f"Error truncando log: {e}")
    
    def close(self):
        """Cierra el WAL y asegura que todos los datos estén escritos."""
        self._close_log()
    
    def __del__(self):
        """Asegura que el log se cierre al destruir el objeto."""
        self.close()

