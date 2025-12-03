"""
Tracker de operaciones para métricas del sistema GFS.

Rastrea operaciones (read, write, append) con timestamps
para calcular throughput y latencia.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque, defaultdict
from dataclasses import dataclass, field


@dataclass
class OperationRecord:
    """Registro de una operación individual."""
    operation_type: str  # 'read', 'write', 'append'
    start_time: float
    end_time: float
    success: bool
    bytes_transferred: int = 0
    chunkserver_id: Optional[str] = None  # Para operaciones que involucran un chunkserver específico
    
    @property
    def latency(self) -> float:
        """Latencia en segundos."""
        return self.end_time - self.start_time


class OperationsTracker:
    """
    Rastrea operaciones del sistema para calcular métricas.
    
    Mantiene un historial de operaciones recientes para calcular:
    - Throughput (operaciones por segundo)
    - Latencia promedio y percentiles
    - Distribución de carga por chunkserver
    """
    
    def __init__(self, history_limit: int = 10000):
        """
        Inicializa el tracker.
        
        Args:
            history_limit: Número máximo de operaciones a mantener en memoria
        """
        self.history_limit = history_limit
        # Historial de operaciones (usar deque para eficiencia)
        self.operations: deque = deque(maxlen=history_limit)
        # Contadores por tipo de operación
        self.counters: Dict[str, int] = defaultdict(int)
        # Contadores por chunkserver
        self.chunkserver_operations: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.chunkserver_bytes: Dict[str, int] = defaultdict(int)
        # Tracking de re-replicación activa
        self.active_replications: Dict[str, float] = {}  # chunk_handle -> start_time
        # Tracking de fallos de chunkservers
        self.chunkserver_failures: Dict[str, List[float]] = defaultdict(list)  # cs_id -> [timestamps]
        # Lock para thread-safety
        import threading
        self._lock = threading.RLock()
    
    def record_operation(self, operation_type: str, start_time: float, end_time: float,
                        success: bool, bytes_transferred: int = 0,
                        chunkserver_id: Optional[str] = None):
        """
        Registra una operación.
        
        Args:
            operation_type: Tipo de operación ('read', 'write', 'append')
            start_time: Timestamp de inicio (time.time())
            end_time: Timestamp de fin (time.time())
            success: Si la operación fue exitosa
            bytes_transferred: Bytes transferidos
            chunkserver_id: ID del chunkserver involucrado (opcional)
        """
        with self._lock:
            record = OperationRecord(
                operation_type=operation_type,
                start_time=start_time,
                end_time=end_time,
                success=success,
                bytes_transferred=bytes_transferred,
                chunkserver_id=chunkserver_id
            )
            self.operations.append(record)
            self.counters[operation_type] += 1
            
            if chunkserver_id:
                self.chunkserver_operations[chunkserver_id][operation_type] += 1
                self.chunkserver_bytes[chunkserver_id] += bytes_transferred
    
    def start_operation(self, operation_type: str) -> float:
        """
        Inicia el tracking de una operación.
        
        Returns:
            Timestamp de inicio para usar con end_operation
        """
        return time.time()
    
    def end_operation(self, operation_type: str, start_time: float, success: bool,
                     bytes_transferred: int = 0, chunkserver_id: Optional[str] = None):
        """
        Finaliza el tracking de una operación.
        
        Args:
            operation_type: Tipo de operación
            start_time: Timestamp de inicio retornado por start_operation
            success: Si la operación fue exitosa
            bytes_transferred: Bytes transferidos
            chunkserver_id: ID del chunkserver involucrado
        """
        end_time = time.time()
        self.record_operation(operation_type, start_time, end_time, success,
                            bytes_transferred, chunkserver_id)
    
    def get_throughput(self, window_seconds: float = 60.0) -> Dict[str, float]:
        """
        Calcula throughput (operaciones por segundo) en una ventana de tiempo.
        
        Args:
            window_seconds: Ventana de tiempo en segundos (default: 60 segundos)
        
        Returns:
            Diccionario con throughput por tipo de operación
        """
        with self._lock:
            cutoff_time = time.time() - window_seconds
            throughput = defaultdict(float)
            
            for op in self.operations:
                if op.start_time >= cutoff_time:
                    throughput[op.operation_type] += 1
            
            # Convertir a operaciones por segundo
            for op_type in throughput:
                throughput[op_type] /= window_seconds
            
            return dict(throughput)
    
    def get_latency_stats(self, operation_type: Optional[str] = None,
                         window_seconds: float = 60.0) -> Dict[str, float]:
        """
        Calcula estadísticas de latencia (promedio, p50, p95, p99).
        
        Args:
            operation_type: Tipo de operación (None para todas)
            window_seconds: Ventana de tiempo en segundos
        
        Returns:
            Diccionario con 'avg', 'p50', 'p95', 'p99' en segundos
        """
        with self._lock:
            cutoff_time = time.time() - window_seconds
            latencies = []
            
            for op in self.operations:
                if op.start_time >= cutoff_time and op.success:
                    if operation_type is None or op.operation_type == operation_type:
                        latencies.append(op.latency)
            
            if not latencies:
                return {
                    'avg': 0.0,
                    'p50': 0.0,
                    'p95': 0.0,
                    'p99': 0.0,
                    'min': 0.0,
                    'max': 0.0
                }
            
            latencies.sort()
            n = len(latencies)
            
            def percentile(p: float) -> float:
                """Calcula el percentil p (0-100)."""
                index = int((p / 100.0) * (n - 1))
                return latencies[index]
            
            return {
                'avg': sum(latencies) / n,
                'p50': percentile(50),
                'p95': percentile(95),
                'p99': percentile(99),
                'min': latencies[0],
                'max': latencies[-1]
            }
    
    def get_chunkserver_load(self) -> Dict[str, Dict]:
        """
        Obtiene la distribución de carga por chunkserver.
        
        Returns:
            Diccionario con estadísticas por chunkserver:
            {
                'cs_id': {
                    'operations': {'read': 10, 'write': 5, 'append': 2},
                    'bytes_transferred': 1024000,
                    'total_operations': 17
                }
            }
        """
        with self._lock:
            load = {}
            for cs_id, ops in self.chunkserver_operations.items():
                total_ops = sum(ops.values())
                load[cs_id] = {
                    'operations': dict(ops),
                    'bytes_transferred': self.chunkserver_bytes.get(cs_id, 0),
                    'total_operations': total_ops
                }
            return load
    
    def start_replication(self, chunk_handle: str):
        """Registra el inicio de una re-replicación."""
        with self._lock:
            self.active_replications[chunk_handle] = time.time()
    
    def end_replication(self, chunk_handle: str):
        """Registra el fin de una re-replicación."""
        with self._lock:
            if chunk_handle in self.active_replications:
                del self.active_replications[chunk_handle]
    
    def get_active_replications(self) -> Dict[str, float]:
        """
        Obtiene las re-replicaciones activas.
        
        Returns:
            Diccionario {chunk_handle: start_time}
        """
        with self._lock:
            return dict(self.active_replications)
    
    def record_chunkserver_failure(self, chunkserver_id: str):
        """Registra un fallo de chunkserver."""
        with self._lock:
            self.chunkserver_failures[chunkserver_id].append(time.time())
            # Mantener solo los últimos 100 fallos por chunkserver
            if len(self.chunkserver_failures[chunkserver_id]) > 100:
                self.chunkserver_failures[chunkserver_id] = \
                    self.chunkserver_failures[chunkserver_id][-100:]
    
    def get_failure_rate(self, chunkserver_id: Optional[str] = None,
                        window_seconds: float = 3600.0) -> float:
        """
        Calcula la tasa de fallos (fallos por hora).
        
        Args:
            chunkserver_id: ID del chunkserver (None para todos)
            window_seconds: Ventana de tiempo en segundos
        
        Returns:
            Tasa de fallos (fallos por hora)
        """
        with self._lock:
            cutoff_time = time.time() - window_seconds
            failures = 0
            
            if chunkserver_id:
                failures = sum(1 for t in self.chunkserver_failures.get(chunkserver_id, [])
                             if t >= cutoff_time)
            else:
                for cs_id, timestamps in self.chunkserver_failures.items():
                    failures += sum(1 for t in timestamps if t >= cutoff_time)
            
            # Convertir a fallos por hora
            hours = window_seconds / 3600.0
            return failures / hours if hours > 0 else 0.0
    
    def get_recent_operations(self, limit: int = 100) -> List[Dict]:
        """
        Obtiene las operaciones más recientes.
        
        Args:
            limit: Número máximo de operaciones a retornar
        
        Returns:
            Lista de diccionarios con información de operaciones
        """
        with self._lock:
            recent = list(self.operations)[-limit:]
            return [
                {
                    'type': op.operation_type,
                    'latency': op.latency,
                    'success': op.success,
                    'bytes': op.bytes_transferred,
                    'chunkserver_id': op.chunkserver_id,
                    'timestamp': op.start_time
                }
                for op in recent
            ]

