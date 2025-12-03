"""
Gestor de procesos para el sistema GFS.

Gestiona el inicio y detención de Master y ChunkServers
como procesos separados.
"""
import subprocess
import time
import signal
import os
import sys
from pathlib import Path
from typing import Dict, Optional, List
import requests


class ProcessManager:
    """
    Gestiona los procesos del sistema GFS (Master y ChunkServers).
    """
    
    def __init__(self, master_port: int = 8000, chunkserver_ports: List[int] = None):
        """
        Inicializa el gestor de procesos.
        
        Args:
            master_port: Puerto del Master
            chunkserver_ports: Lista de puertos para los ChunkServers (por defecto [8001, 8002, 8003])
        """
        self.master_port = master_port
        self.chunkserver_ports = chunkserver_ports or [8001, 8002, 8003]
        self.master_address = f"http://localhost:{master_port}"
        
        # PIDs de los procesos
        self.master_process: Optional[subprocess.Popen] = None
        self.chunkserver_processes: Dict[str, subprocess.Popen] = {}
        
        # Mapeo de ChunkServer ID a puerto
        self.chunkserver_port_map: Dict[str, int] = {}
        
        # Información de ChunkServers quitados (para poder restaurarlos)
        # Guarda: {chunkserver_id: {"port": int, "data_dir": str}}
        self.removed_chunkservers: Dict[str, dict] = {}
        
        # Puerto base para ChunkServers (se incrementa automáticamente)
        self.next_chunkserver_port = max(self.chunkserver_ports) + 1 if self.chunkserver_ports else 8001
        
        # Obtener ruta base del proyecto
        self.base_path = Path(__file__).parent.parent.parent.parent
    
    def start_master(self) -> bool:
        """
        Inicia el Master en un proceso separado.
        
        Returns:
            True si se inició correctamente, False en caso contrario
        """
        if self.master_process and self.master_process.poll() is None:
            print("Master ya está ejecutándose")
            return True
        
        try:
            # Ruta al script run_master.py
            master_script = self.base_path / "mini_gfs" / "run_master.py"
            
            # Verificar que el script existe
            if not master_script.exists():
                print(f"Error: No se encuentra el script {master_script}")
                return False
            
            print(f"Iniciando Master...")
            
            # Iniciar proceso - usar DEVNULL para evitar bloqueos con PIPE
            self.master_process = subprocess.Popen(
                [sys.executable, str(master_script)],
                stdout=subprocess.DEVNULL,  # Cambiar de PIPE a DEVNULL
                stderr=subprocess.PIPE,  # Mantener stderr para errores
                cwd=str(self.base_path)
            )
            
            # Esperar un poco para que el proceso se inicie
            time.sleep(2)
            
            # Verificar que el proceso sigue vivo
            if self.master_process.poll() is not None:
                # El proceso terminó inmediatamente, leer stderr
                try:
                    stderr_output = self.master_process.stderr.read().decode('utf-8') if self.master_process.stderr else "Sin mensaje de error"
                    print(f"Error: Master terminó inmediatamente")
                    print(f"Stderr: {stderr_output}")
                except:
                    pass
                self.master_process = None
                return False
            
            print(f"Master proceso iniciado (PID: {self.master_process.pid}), esperando que esté listo...")
            
            # Esperar a que el Master esté listo (aumentar timeout a 60 segundos)
            if self._wait_for_master(timeout=60):
                print(f"✅ Master iniciado correctamente (PID: {self.master_process.pid})")
                return True
            else:
                # Verificar si el proceso sigue vivo
                if self.master_process.poll() is not None:
                    try:
                        stderr_output = self.master_process.stderr.read().decode('utf-8') if self.master_process.stderr else "Sin mensaje de error"
                        print(f"Error: Master terminó durante la espera")
                        print(f"Stderr: {stderr_output}")
                    except:
                        pass
                else:
                    print("Error: Master no respondió a tiempo (pero el proceso sigue ejecutándose)")
                self.stop_master()
                return False
                
        except Exception as e:
            print(f"Error iniciando Master: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start_chunkserver(self, port: int, chunkserver_id: str, data_dir: str) -> bool:
        """
        Inicia un ChunkServer en un proceso separado.
        
        Args:
            port: Puerto del ChunkServer
            chunkserver_id: ID del ChunkServer
            data_dir: Directorio de datos del ChunkServer
        
        Returns:
            True si se inició correctamente, False en caso contrario
        """
        if chunkserver_id in self.chunkserver_processes:
            proc = self.chunkserver_processes[chunkserver_id]
            if proc.poll() is None:
                print(f"ChunkServer {chunkserver_id} ya está ejecutándose")
                return True
        
        try:
            # Crear directorio de datos si no existe
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            
            # Ruta al script run_chunkserver.py
            chunkserver_script = self.base_path / "mini_gfs" / "run_chunkserver.py"
            
            # Verificar que el script existe
            if not chunkserver_script.exists():
                print(f"Error: No se encuentra el script {chunkserver_script}")
                return False
            
            # Iniciar proceso - usar DEVNULL para evitar bloqueos con PIPE
            import subprocess
            proc = subprocess.Popen(
                [
                    sys.executable, str(chunkserver_script),
                    "--port", str(port),
                    "--id", chunkserver_id,
                    "--data-dir", data_dir,
                    "--master", self.master_address
                ],
                stdout=subprocess.DEVNULL,  # Cambiar de PIPE a DEVNULL para evitar bloqueos
                stderr=subprocess.PIPE,  # Mantener stderr para capturar errores
                cwd=str(self.base_path)
            )
            
            self.chunkserver_processes[chunkserver_id] = proc
            self.chunkserver_port_map[chunkserver_id] = port
            
            # Esperar y verificar que el proceso sigue ejecutándose
            time.sleep(3)  # Aumentar tiempo de espera
            
            # Verificar que el proceso sigue vivo
            if proc.poll() is not None:
                # El proceso terminó, leer stderr para ver el error
                try:
                    stderr_output = proc.stderr.read().decode('utf-8') if proc.stderr else "Sin mensaje de error"
                    print(f"Error: ChunkServer {chunkserver_id} terminó inmediatamente")
                    print(f"Stderr: {stderr_output}")
                except:
                    pass
                # Limpiar el mapeo si falló
                if chunkserver_id in self.chunkserver_port_map:
                    del self.chunkserver_port_map[chunkserver_id]
                return False
            
            # Verificar que el ChunkServer esté respondiendo
            chunkserver_address = f"http://localhost:{port}"
            if self._wait_for_chunkserver(chunkserver_address, timeout=10):
                print(f"ChunkServer {chunkserver_id} iniciado correctamente (PID: {proc.pid}, Puerto: {port})")
                # Actualizar el siguiente puerto disponible
                if port >= self.next_chunkserver_port:
                    self.next_chunkserver_port = port + 1
                return True
            else:
                print(f"Advertencia: ChunkServer {chunkserver_id} iniciado pero no responde en {chunkserver_address}")
                # Aún así retornar True si el proceso está vivo
                if proc.poll() is None:
                    # Actualizar el siguiente puerto disponible
                    if port >= self.next_chunkserver_port:
                        self.next_chunkserver_port = port + 1
                    return True
                # Limpiar el mapeo si falló
                if chunkserver_id in self.chunkserver_port_map:
                    del self.chunkserver_port_map[chunkserver_id]
                return False
            
        except Exception as e:
            print(f"Error iniciando ChunkServer {chunkserver_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start_all(self) -> bool:
        """
        Inicia Master + 3 ChunkServers automáticamente.
        
        Returns:
            True si todos se iniciaron correctamente, False en caso contrario
        """
        print("Iniciando sistema GFS...")
        
        # Verificar que los puertos no estén en uso
        ports_in_use = []
        if self._is_port_in_use(self.master_port):
            ports_in_use.append(f"{self.master_port} (Master)")
        
        for port in self.chunkserver_ports:
            if self._is_port_in_use(port):
                ports_in_use.append(f"{port} (ChunkServer)")
        
        if ports_in_use:
            print(f"⚠️  Advertencia: Los siguientes puertos están en uso: {', '.join(ports_in_use)}")
            print("Intentando limpiar procesos huérfanos...")
            self.kill_all_processes()
            time.sleep(2)  # Esperar a que los puertos se liberen
            
            # Verificar de nuevo
            ports_still_in_use = []
            if self._is_port_in_use(self.master_port):
                ports_still_in_use.append(f"{self.master_port} (Master)")
            
            for port in self.chunkserver_ports:
                if self._is_port_in_use(port):
                    ports_still_in_use.append(f"{port} (ChunkServer)")
            
            if ports_still_in_use:
                print(f"❌ Error: Los siguientes puertos siguen en uso después de limpiar: {', '.join(ports_still_in_use)}")
                print("Por favor, detén manualmente los procesos que usan estos puertos.")
                return False
            else:
                print("✅ Puertos liberados correctamente")
        
        # Iniciar Master primero
        if not self.start_master():
            print("Error: No se pudo iniciar el Master")
            return False
        
        # Esperar un poco para que el Master esté completamente listo
        time.sleep(3)
        
        # Iniciar ChunkServers
        success = True
        failed_chunkservers = []
        
        for i, port in enumerate(self.chunkserver_ports, 1):
            chunkserver_id = f"cs{i}"
            data_dir = str(self.base_path / "data" / f"chunkserver{i}")
            
            print(f"Iniciando {chunkserver_id} en puerto {port}...")
            if not self.start_chunkserver(port, chunkserver_id, data_dir):
                success = False
                failed_chunkservers.append(chunkserver_id)
                print(f"❌ Error iniciando {chunkserver_id}")
            else:
                print(f"✅ {chunkserver_id} iniciado correctamente")
                # Registrar el puerto usado
                self.chunkserver_port_map[chunkserver_id] = port
                # Actualizar el siguiente puerto disponible
                if port >= self.next_chunkserver_port:
                    self.next_chunkserver_port = port + 1
        
        if success:
            print("✅ Sistema GFS iniciado correctamente (Master + 3 ChunkServers)")
        else:
            print(f"⚠️  Advertencia: Algunos ChunkServers no se iniciaron: {', '.join(failed_chunkservers)}")
        
        return success
    
    def stop_master(self):
        """Detiene el Master."""
        if self.master_process:
            try:
                # Enviar señal SIGTERM
                self.master_process.terminate()
                # Esperar hasta 5 segundos
                try:
                    self.master_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Si no termina, forzar
                    self.master_process.kill()
                    self.master_process.wait()
                print("Master detenido")
            except Exception as e:
                print(f"Error deteniendo Master: {e}")
            finally:
                self.master_process = None
    
    def stop_chunkserver(self, chunkserver_id: str, save_info: bool = False):
        """
        Detiene un ChunkServer específico.
        
        Args:
            chunkserver_id: ID del ChunkServer a detener
            save_info: Si es True, guarda la información del ChunkServer para poder restaurarlo después
        """
        if chunkserver_id in self.chunkserver_processes:
            proc = self.chunkserver_processes[chunkserver_id]
            
            # Guardar información antes de eliminar si se solicita
            if save_info:
                port = self.chunkserver_port_map.get(chunkserver_id)
                data_dir = str(self.base_path / "data" / chunkserver_id)
                self.removed_chunkservers[chunkserver_id] = {
                    "port": port,
                    "data_dir": data_dir
                }
            
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                print(f"ChunkServer {chunkserver_id} detenido")
            except Exception as e:
                print(f"Error deteniendo ChunkServer {chunkserver_id}: {e}")
            finally:
                if chunkserver_id in self.chunkserver_processes:
                    del self.chunkserver_processes[chunkserver_id]
                if chunkserver_id in self.chunkserver_port_map:
                    del self.chunkserver_port_map[chunkserver_id]
    
    def stop_all(self):
        """Detiene todos los procesos (Master + ChunkServers)."""
        print("Deteniendo sistema GFS...")
        
        # Detener ChunkServers primero
        for chunkserver_id in list(self.chunkserver_processes.keys()):
            self.stop_chunkserver(chunkserver_id)
        
        # Detener Master
        self.stop_master()
        
        print("Sistema GFS detenido")
    
    def kill_all_processes(self):
        """
        Mata todos los procesos relacionados con GFS que puedan estar colgados.
        Esto es una medida de seguridad para liberar puertos.
        """
        try:
            import psutil
            import os
            
            current_pid = os.getpid()
            killed_count = 0
            
            # Buscar procesos relacionados con GFS
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Saltar el proceso actual
                    if proc.info['pid'] == current_pid:
                        continue
                    
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue
                    
                    # Buscar procesos de Python que ejecuten run_master.py o run_chunkserver.py
                    cmdline_str = ' '.join(cmdline)
                    if 'run_master.py' in cmdline_str or 'run_chunkserver.py' in cmdline_str:
                        try:
                            print(f"Matando proceso huérfano: PID {proc.info['pid']} - {cmdline_str[:100]}")
                            proc.kill()
                            killed_count += 1
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if killed_count > 0:
                print(f"✅ {killed_count} proceso(s) huérfano(s) eliminado(s)")
            
        except ImportError:
            # psutil no está instalado, usar método alternativo
            print("psutil no disponible, usando método alternativo para liberar puertos...")
            self._kill_processes_by_port()
        except Exception as e:
            print(f"Error matando procesos huérfanos con psutil: {e}")
            # Intentar método alternativo
            self._kill_processes_by_port()
    
    def _kill_processes_by_port(self):
        """
        Método alternativo para matar procesos por puerto (sin psutil).
        """
        import subprocess
        import platform
        
        ports_to_check = [self.master_port] + self.chunkserver_ports
        killed_count = 0
        
        for port in ports_to_check:
            try:
                if platform.system() == 'Darwin':  # macOS
                    # Usar lsof para encontrar procesos usando el puerto
                    result = subprocess.run(
                        ['lsof', '-ti', f':{port}'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid and pid.isdigit():
                                try:
                                    subprocess.run(['kill', '-9', pid], check=False, timeout=2)
                                    print(f"  Proceso en puerto {port} (PID {pid}) eliminado")
                                    killed_count += 1
                                except:
                                    pass
                elif platform.system() == 'Linux':
                    # Usar fuser o lsof
                    try:
                        result = subprocess.run(
                            ['fuser', '-k', f'{port}/tcp'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            killed_count += 1
                    except FileNotFoundError:
                        # Intentar con lsof
                        result = subprocess.run(
                            ['lsof', '-ti', f':{port}'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            pids = result.stdout.strip().split('\n')
                            for pid in pids:
                                if pid and pid.isdigit():
                                    try:
                                        subprocess.run(['kill', '-9', pid], check=False, timeout=2)
                                        killed_count += 1
                                    except:
                                        pass
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                # Ignorar errores silenciosamente
                pass
        
        if killed_count > 0:
            print(f"✅ {killed_count} proceso(s) en puertos eliminado(s)")
        else:
            print("  No se encontraron procesos en los puertos")
    
    def get_status(self) -> Dict:
        """
        Obtiene el estado de todos los procesos.
        
        Returns:
            Diccionario con el estado de cada proceso
        """
        status = {
            "master": {
                "running": False,
                "pid": None
            },
            "chunkservers": {}
        }
        
        # Estado del Master
        if self.master_process:
            if self.master_process.poll() is None:
                status["master"]["running"] = True
                status["master"]["pid"] = self.master_process.pid
            else:
                # Proceso terminado
                self.master_process = None
        
        # Estado de ChunkServers
        for chunkserver_id, proc in list(self.chunkserver_processes.items()):
            if proc.poll() is None:
                status["chunkservers"][chunkserver_id] = {
                    "running": True,
                    "pid": proc.pid
                }
            else:
                # Proceso terminado
                del self.chunkserver_processes[chunkserver_id]
                status["chunkservers"][chunkserver_id] = {
                    "running": False,
                    "pid": None
                }
        
        return status
    
    def _wait_for_master(self, timeout: int = 60) -> bool:
        """
        Espera a que el Master esté listo y respondiendo.
        
        Args:
            timeout: Tiempo máximo de espera en segundos
        
        Returns:
            True si el Master está listo, False en caso contrario
        """
        start_time = time.time()
        attempts = 0
        
        while time.time() - start_time < timeout:
            # Verificar que el proceso sigue vivo
            if self.master_process and self.master_process.poll() is not None:
                print("Master proceso terminó durante la espera")
                return False
            
            try:
                # Intentar hacer una petición simple al Master
                # Primero intentar con un endpoint simple para verificar que el servidor responde
                try:
                    response = requests.get(
                        f"{self.master_address}/system_state",
                        timeout=3
                    )
                    if response.status_code == 200:
                        # Verificar que la respuesta sea válida JSON
                        try:
                            data = response.json()
                            if data.get("success", False):
                                return True
                        except ValueError as e:
                            # JSON inválido, pero el servidor está respondiendo
                            print(f"Advertencia: Master responde pero JSON inválido: {e}")
                            return True
                    elif response.status_code == 404:
                        # 404 significa que el servidor está respondiendo pero el endpoint no existe
                        # Esto no debería pasar, pero significa que el servidor está activo
                        print("Advertencia: Master responde pero endpoint no encontrado")
                        return True
                except requests.exceptions.ConnectionError as e:
                    # El servidor aún no está listo, continuar esperando
                    pass
                except requests.exceptions.Timeout:
                    # Timeout en la petición, continuar esperando
                    pass
            except Exception as e:
                # Otros errores pueden ser temporales
                pass
            
            attempts += 1
            if attempts % 10 == 0:  # Cada 5 segundos (10 * 0.5)
                elapsed = time.time() - start_time
                print(f"Esperando Master... ({elapsed:.1f}s/{timeout}s)")
            
            time.sleep(0.5)
        
        return False
    
    def _is_port_in_use(self, port: int) -> bool:
        """
        Verifica si un puerto está en uso.
        
        Args:
            port: Puerto a verificar
        
        Returns:
            True si el puerto está en uso, False en caso contrario
        """
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return False
            except OSError:
                return True
    
    def _wait_for_chunkserver(self, chunkserver_address: str, timeout: int = 10) -> bool:
        """
        Espera a que un ChunkServer esté listo y respondiendo.
        
        Args:
            chunkserver_address: Dirección del ChunkServer
            timeout: Tiempo máximo de espera en segundos
        
        Returns:
            True si el ChunkServer está listo, False en caso contrario
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Intentar hacer una petición a un endpoint que debería existir
                # Los ChunkServers tienen endpoints POST, pero podemos verificar
                # que el servidor HTTP esté respondiendo con cualquier petición
                # Usar un endpoint que sabemos que existe (aunque falle, significa que el servidor responde)
                response = requests.post(
                    f"{chunkserver_address}/read_chunk",
                    json={"chunk_handle": "test", "offset": 0, "length": 0},
                    timeout=1
                )
                # Cualquier respuesta (incluso error) significa que el servidor está activo
                return True
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                # El servidor aún no está listo
                pass
            except Exception:
                # Otros errores (como 400, 404) significan que el servidor está activo
                return True
            
            time.sleep(0.5)
        
        return False
    
    def add_chunkserver(self) -> dict:
        """
        Agrega un nuevo ChunkServer dinámicamente con puerto automático e incremental.
        
        Returns:
            Diccionario con el resultado de la operación
        """
        # Encontrar el siguiente puerto disponible
        port = self.next_chunkserver_port
        while self._is_port_in_use(port):
            port += 1
        
        # Generar ID único para el ChunkServer
        chunkserver_id = f"cs{len(self.chunkserver_processes) + 1}"
        # Asegurarse de que el ID sea único
        counter = 1
        while chunkserver_id in self.chunkserver_processes:
            chunkserver_id = f"cs{len(self.chunkserver_processes) + counter}"
            counter += 1
        
        # Crear directorio de datos
        data_dir = str(self.base_path / "data" / chunkserver_id)
        
        print(f"Agregando ChunkServer {chunkserver_id} en puerto {port}...")
        
        if self.start_chunkserver(port, chunkserver_id, data_dir):
            return {
                "success": True,
                "chunkserver_id": chunkserver_id,
                "port": port,
                "message": f"ChunkServer {chunkserver_id} agregado correctamente en puerto {port}"
            }
        else:
            return {
                "success": False,
                "message": f"Error agregando ChunkServer {chunkserver_id}"
            }
    
    def remove_chunkserver(self, chunkserver_id: str) -> dict:
        """
        Quita un ChunkServer del sistema (pero guarda su información para poder restaurarlo).
        
        Args:
            chunkserver_id: ID del ChunkServer a quitar
        
        Returns:
            Diccionario con el resultado de la operación
        """
        if chunkserver_id not in self.chunkserver_processes:
            return {
                "success": False,
                "message": f"ChunkServer {chunkserver_id} no está ejecutándose"
            }
        
        print(f"Quitando ChunkServer {chunkserver_id}...")
        # Guardar información antes de detener
        self.stop_chunkserver(chunkserver_id, save_info=True)
        
        return {
            "success": True,
            "chunkserver_id": chunkserver_id,
            "message": f"ChunkServer {chunkserver_id} quitado correctamente (puede ser restaurado)"
        }
    
    def restore_chunkserver(self, chunkserver_id: str) -> dict:
        """
        Restaura/reinicia un ChunkServer que fue quitado previamente.
        
        Args:
            chunkserver_id: ID del ChunkServer a restaurar
        
        Returns:
            Diccionario con el resultado de la operación
        """
        if chunkserver_id not in self.removed_chunkservers:
            return {
                "success": False,
                "message": f"ChunkServer {chunkserver_id} no está en la lista de ChunkServers quitados"
            }
        
        if chunkserver_id in self.chunkserver_processes:
            return {
                "success": False,
                "message": f"ChunkServer {chunkserver_id} ya está ejecutándose"
            }
        
        # Obtener información guardada
        info = self.removed_chunkservers[chunkserver_id]
        port = info["port"]
        data_dir = info["data_dir"]
        
        # Verificar que el puerto no esté en uso
        if self._is_port_in_use(port):
            return {
                "success": False,
                "message": f"El puerto {port} está en uso. No se puede restaurar {chunkserver_id}"
            }
        
        print(f"Restaurando ChunkServer {chunkserver_id} en puerto {port}...")
        
        if self.start_chunkserver(port, chunkserver_id, data_dir):
            # Eliminar de la lista de quitados
            del self.removed_chunkservers[chunkserver_id]
            return {
                "success": True,
                "chunkserver_id": chunkserver_id,
                "port": port,
                "message": f"ChunkServer {chunkserver_id} restaurado correctamente en puerto {port}"
            }
        else:
            return {
                "success": False,
                "message": f"Error restaurando ChunkServer {chunkserver_id}"
            }
    
    def get_chunkservers_info(self) -> dict:
        """
        Obtiene información de todos los ChunkServers activos y quitados.
        
        Returns:
            Diccionario con información de cada ChunkServer (activos y quitados)
        """
        chunkservers_info = {}
        
        # ChunkServers activos
        for chunkserver_id, proc in self.chunkserver_processes.items():
            port = self.chunkserver_port_map.get(chunkserver_id, None)
            chunkservers_info[chunkserver_id] = {
                "id": chunkserver_id,
                "port": port,
                "running": proc.poll() is None,
                "pid": proc.pid if proc.poll() is None else None,
                "status": "running"
            }
        
        # ChunkServers quitados (que pueden ser restaurados)
        for chunkserver_id, info in self.removed_chunkservers.items():
            chunkservers_info[chunkserver_id] = {
                "id": chunkserver_id,
                "port": info["port"],
                "running": False,
                "pid": None,
                "status": "stopped",
                "can_restore": True
            }
        
        return chunkservers_info

