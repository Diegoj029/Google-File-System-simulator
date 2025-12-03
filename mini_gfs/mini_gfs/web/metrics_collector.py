"""
Recolector de métricas del sistema GFS.

Recolecta métricas periódicamente del Master y las almacena
para visualización y análisis.
"""
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque


class MetricsCollector:
    """
    Recolecta y almacena métricas del sistema GFS.
    """
    
    def __init__(self, master_address: str = "http://localhost:8000", 
                 history_limit: int = 1000, metrics_dir: str = "data/metrics"):
        """
        Inicializa el recolector de métricas.
        
        Args:
            master_address: Dirección del Master
            history_limit: Número máximo de métricas a mantener en memoria
            metrics_dir: Directorio para guardar métricas en disco
        """
        self.master_address = master_address
        self.history_limit = history_limit
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        # Almacenar métricas en memoria (usar deque para eficiencia)
        self.metrics_history: deque = deque(maxlen=history_limit)
    
    def collect(self) -> Optional[Dict]:
        """
        Recolecta métricas actuales del Master.
        
        Returns:
            Diccionario con las métricas o None si falla
        """
        try:
            # Obtener estado del sistema
            try:
                response = requests.get(
                    f"{self.master_address}/system_state",
                    timeout=5
                )
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                # El Master no está disponible o no responde
                return None
            
            if response.status_code != 200:
                return None
            
            try:
                system_state = response.json()
            except (ValueError, KeyError) as e:
                # Error al parsear JSON
                return None
            
            # Verificar que la respuesta sea exitosa
            if not system_state.get("success", False):
                return None
            
            # Calcular métricas
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "chunkservers_alive": 0,
                "chunkservers_dead": 0,
                "total_chunks": 0,
                "under_replicated_chunks": 0,
                "total_files": 0,
                "chunkservers": {},
                "chunk_distribution": {}
            }
            
            # Procesar ChunkServers
            chunkservers = system_state.get("chunkservers", {})
            for cs_id, cs_info in chunkservers.items():
                if cs_info.get("is_alive", False):
                    metrics["chunkservers_alive"] += 1
                else:
                    metrics["chunkservers_dead"] += 1
                
                chunks_count = len(cs_info.get("chunks", []))
                metrics["chunkservers"][cs_id] = {
                    "is_alive": cs_info.get("is_alive", False),
                    "chunks_count": chunks_count,
                    "last_heartbeat": cs_info.get("last_heartbeat")
                }
                metrics["chunk_distribution"][cs_id] = chunks_count
            
            # Procesar chunks
            chunks = system_state.get("chunks", {})
            metrics["total_chunks"] = len(chunks)
            
            # Contar chunks sub-replicados
            replication_factor = system_state.get("replication_factor", 3)
            for chunk_handle, chunk_info in chunks.items():
                replicas_count = len(chunk_info.get("replicas", []))
                if replicas_count < replication_factor:
                    metrics["under_replicated_chunks"] += 1
            
            # Procesar archivos
            files = system_state.get("files", {})
            metrics["total_files"] = len(files)
            
            # Agregar a historial
            self.metrics_history.append(metrics)
            
            # Guardar periódicamente a disco (cada 10 métricas)
            if len(self.metrics_history) % 10 == 0:
                self._save_to_disk()
            
            return metrics
            
        except Exception as e:
            # Solo imprimir errores no relacionados con conexión
            # (los errores de conexión ya se manejan arriba)
            if not isinstance(e, (requests.exceptions.ConnectionError,
                                 requests.exceptions.Timeout,
                                 requests.exceptions.RequestException)):
                print(f"Error recolectando métricas: {e}")
            return None
    
    def get_current(self) -> Optional[Dict]:
        """
        Obtiene las métricas más recientes.
        
        Returns:
            Diccionario con las métricas más recientes o None
        """
        if not self.metrics_history:
            return None
        return self.metrics_history[-1]
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        """
        Obtiene el historial de métricas.
        
        Args:
            limit: Número máximo de métricas a retornar
        
        Returns:
            Lista de métricas (más recientes primero)
        """
        return list(self.metrics_history)[-limit:]
    
    def _save_to_disk(self):
        """Guarda las métricas a disco en formato JSON."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.metrics_dir / f"metrics_{timestamp}.json"
            
            with open(file_path, 'w') as f:
                json.dump(list(self.metrics_history), f, indent=2)
            
        except Exception as e:
            print(f"Error guardando métricas a disco: {e}")

