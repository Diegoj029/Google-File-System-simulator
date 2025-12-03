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
            
            # Obtener métricas avanzadas del Master
            try:
                metrics_response = requests.get(
                    f"{self.master_address}/metrics",
                    timeout=5
                )
                if metrics_response.status_code == 200:
                    advanced_metrics = metrics_response.json()
                    if advanced_metrics.get("success"):
                        # Usar métricas avanzadas si están disponibles
                        metrics = {
                            "timestamp": datetime.now().isoformat(),
                            # Métricas básicas
                            "chunkservers_alive": advanced_metrics.get("chunkservers_alive", 0),
                            "chunkservers_dead": advanced_metrics.get("chunkservers_dead", 0),
                            "total_chunks": advanced_metrics.get("total_chunks", 0),
                            "under_replicated_chunks": advanced_metrics.get("under_replicated_chunks", 0),
                            "total_files": advanced_metrics.get("total_files", 0),
                            # Throughput (operaciones por segundo)
                            "throughput": advanced_metrics.get("throughput", {}),
                            # Latencia (promedio y percentiles)
                            "latency": advanced_metrics.get("latency", {}),
                            # Distribución de carga por chunkserver
                            "chunkserver_load": advanced_metrics.get("chunkserver_load", {}),
                            # Re-replicaciones activas
                            "active_replications": advanced_metrics.get("active_replications", {}),
                            # Tasa de fallos (fallos por hora)
                            "failure_rate": advanced_metrics.get("failure_rate", 0.0),
                            # Fragmentación de archivos
                            "fragmentation": advanced_metrics.get("fragmentation", {}),
                            # Réplicas obsoletas
                            "stale_replicas": advanced_metrics.get("stale_replicas", {}),
                            # Información detallada de chunkservers (del system_state)
                            "chunkservers": {},
                            "chunk_distribution": {}
                        }
                    else:
                        # Fallback a cálculo manual
                        metrics = self._calculate_basic_metrics(system_state)
                else:
                    # Fallback a cálculo manual
                    metrics = self._calculate_basic_metrics(system_state)
            except Exception as e:
                # Fallback a cálculo manual si falla la obtención de métricas avanzadas
                metrics = self._calculate_basic_metrics(system_state)
            
            # Procesar ChunkServers (siempre necesario para información detallada)
            if "chunkservers" not in metrics or not metrics["chunkservers"]:
                metrics["chunkservers"] = {}
                metrics["chunk_distribution"] = {}
            
            # Procesar ChunkServers (siempre necesario para información detallada)
            chunkservers = system_state.get("chunkservers", {})
            for cs_id, cs_info in chunkservers.items():
                chunks_count = len(cs_info.get("chunks", []))
                metrics["chunkservers"][cs_id] = {
                    "is_alive": cs_info.get("is_alive", False),
                    "chunks_count": chunks_count,
                    "last_heartbeat": cs_info.get("last_heartbeat")
                }
                metrics["chunk_distribution"][cs_id] = chunks_count
            
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
    
    def _calculate_basic_metrics(self, system_state: dict) -> dict:
        """
        Calcula métricas básicas desde system_state (fallback).
        
        Args:
            system_state: Estado del sistema obtenido del Master
        
        Returns:
            Diccionario con métricas básicas
        """
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "chunkservers_alive": 0,
            "chunkservers_dead": 0,
            "total_chunks": 0,
            "under_replicated_chunks": 0,
            "total_files": 0,
            "throughput": {},
            "latency": {},
            "chunkserver_load": {},
            "active_replications": {"count": 0, "chunks": []},
            "failure_rate": 0.0,
            "fragmentation": {},
            "stale_replicas": {},
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
        
        return metrics
    
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

