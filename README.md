# Mini Google File System (GFS)

Un sistema de archivos distribuido educativo inspirado en el Google File System (Ghemawat et al., SOSP 2003).

Este es un proyecto educativo que implementa los conceptos principales de GFS de forma simplificada:
- Un Master central que mantiene metadatos en memoria
- Múltiples ChunkServers que almacenan chunks en disco local
- Un Cliente CLI para operaciones de archivos
- Replicación, leases con primary chunkserver para escrituras, y record append simplificado

## Guía Rápida

**¿Quieres probar toda la funcionalidad?** Consulta la **[Guía Rápida (QUICKGUIDE.md)](QUICKGUIDE.md)** con más de 25 ejemplos prácticos y escenarios de prueba que cubren todas las funcionalidades del simulador, incluyendo operaciones básicas, características avanzadas, pruebas de recuperación, concurrencia y replicación.

---

## Stack Tecnológico

**Python 3.11+** | **requests**, **pyyaml** | **HTTP/JSON** | **Threading** | **WAL + Snapshots JSON**

---

## Características

### Características Principales

- **Master único**: Coordina todas las operaciones y mantiene metadatos en memoria
- **ChunkServers múltiples**: Almacenan chunks replicados en disco local
- **Replicación**: Cada chunk se replica en múltiples ChunkServers (por defecto 3)
- **Leases**: El Master otorga leases a un ChunkServer para actuar como primary
- **Record Append**: Operación atómica para añadir records al final de archivos
- **Detección de fallos**: El Master detecta ChunkServers muertos mediante heartbeats
- **Re-replicación**: Automática cuando un chunk tiene menos réplicas de las requeridas

### Características Avanzadas (Implementadas)

- **Versionado de chunks**: Cada chunk tiene un número de versión que se incrementa en mutaciones para detectar réplicas obsoletas
- **Checksums de integridad**: Verificación de integridad de datos mediante checksums de 32 bits por bloques de 64KB
- **Snapshot de archivos**: Creación instantánea de snapshots usando copy-on-write
- **Garbage collection**: Eliminación automática de chunks huérfanos
- **Data pipeline**: Transferencia eficiente de datos en cadena (Cliente → Réplica1 → Réplica2 → Réplica3)
- **Awareness de racks**: Distribución de réplicas entre racks diferentes para tolerancia a fallos
- **Operaciones de namespace**: Rename, delete y list de archivos/directorios
- **Tamaño de chunk configurable**: 64 MB por defecto (como en GFS original)

## Requisitos

- Python 3.11 o superior
- Dependencias: `requests`, `pyyaml`

## Instalación

1. Instalar dependencias:

```bash
pip install -r requirements.txt
```

O instalar manualmente:

```bash
pip install requests pyyaml
```

## Estructura del Proyecto

```
mini_gfs/
  mini_gfs/
    master/          # Código del Master
      master.py      # Lógica principal del Master
      metadata.py    # Gestión de metadatos
      api.py         # API HTTP del Master
    chunkserver/     # Código del ChunkServer
      chunkserver.py # Lógica principal del ChunkServer
      storage.py     # Almacenamiento local de chunks
      api.py         # API HTTP del ChunkServer
    client/          # Código del Cliente CLI
      cli.py         # Interfaz de línea de comandos
      client_api.py  # API para comunicarse con Master/ChunkServers
    common/          # Tipos y utilidades compartidas
      types.py       # Dataclasses y tipos compartidos
      config.py      # Carga de configuración YAML
  configs/           # Archivos de configuración YAML
    master.yaml      # Configuración del Master
    chunkserver.yaml # Configuración base de ChunkServers
  data/              # Datos persistentes
    master/          # Snapshots de metadatos del Master
    chunks/          # Chunks almacenados por ChunkServer
  scripts/           # Scripts de ejecución
    run_master.sh
    run_chunkserver*.sh
    run_client.sh
  tests/             # Tests unitarios
    test_metadata.py # Tests de metadatos
  run_master.py      # Script principal para ejecutar Master
  run_chunkserver.py # Script principal para ejecutar ChunkServer
  run_client.py      # Script principal para ejecutar Cliente
  The Google File System.pdf  # Paper completo de GFS (SOSP 2003)
```

## Uso

### 1. Iniciar el Master

En una terminal:

```bash
python3 mini_gfs/run_master.py
```

O usando el script:

```bash
./scripts/run_master.sh
```

El Master se iniciará en `http://localhost:8000` por defecto.

### 2. Iniciar ChunkServers

En terminales separadas, iniciar al menos 3 ChunkServers:

```bash
# Terminal 2
python3 mini_gfs/run_chunkserver.py --port 8001 --id cs1 --data-dir data/chunks/cs1

# Terminal 3
python3 mini_gfs/run_chunkserver.py --port 8002 --id cs2 --data-dir data/chunks/cs2

# Terminal 4
python3 mini_gfs/run_chunkserver.py --port 8003 --id cs3 --data-dir data/chunks/cs3
```

O usando los scripts:

```bash
./scripts/run_chunkserver1.sh
./scripts/run_chunkserver2.sh
./scripts/run_chunkserver3.sh
```

### 3. Usar el Cliente CLI

Una vez que el Master y los ChunkServers estén corriendo, puedes usar el cliente:

```bash
# Crear un archivo
python3 mini_gfs/run_client.py create /test.txt

# Escribir datos
python3 mini_gfs/run_client.py write /test.txt 0 "Hello, World!"

# Leer datos
python3 mini_gfs/run_client.py read /test.txt 0 12

# Añadir datos al final (record append)
python3 mini_gfs/run_client.py append /test.txt "More data here"

# Crear snapshot de archivo
python3 mini_gfs/run_client.py snapshot /test.txt /test.txt.snapshot

# Renombrar archivo
python3 mini_gfs/run_client.py rename /test.txt /renamed.txt

# Listar archivos en directorio
python3 mini_gfs/run_client.py listdir /

# Eliminar archivo
python3 mini_gfs/run_client.py delete /renamed.txt

# Listar información del archivo
python3 mini_gfs/run_client.py ls /test.txt
```

**Alternativa:** Si instalas el paquete en modo desarrollo (`pip install -e .`), puedes usar:
```bash
python3 -m mini_gfs.client.cli create /test.txt
```

## Demo: Escenario Completo

### Paso 1: Iniciar el sistema

**Terminal 1 - Master:**
```bash
python3 mini_gfs/run_master.py
```

**Terminal 2 - ChunkServer 1:**
```bash
python3 mini_gfs/run_chunkserver.py --port 8001 --id cs1 --data-dir data/chunks/cs1
```

**Terminal 3 - ChunkServer 2:**
```bash
python3 mini_gfs/run_chunkserver.py --port 8002 --id cs2 --data-dir data/chunks/cs2
```

**Terminal 4 - ChunkServer 3:**
```bash
python3 mini_gfs/run_chunkserver.py --port 8003 --id cs3 --data-dir data/chunks/cs3
```

### Paso 2: Crear y escribir en un archivo

**Terminal 5 - Cliente:**
```bash
# Crear archivo
python3 mini_gfs/run_client.py create /demo.txt

# Escribir datos iniciales
python3 mini_gfs/run_client.py write /demo.txt 0 "Inicio del archivo demo\n"

# Ver información
python3 mini_gfs/run_client.py ls /demo.txt
```

### Paso 3: Añadir múltiples records

```bash
# Añadir varios records (simulando múltiples clientes)
python3 mini_gfs/run_client.py append /demo.txt "Record 1\n"
python3 mini_gfs/run_client.py append /demo.txt "Record 2\n"
python3 mini_gfs/run_client.py append /demo.txt "Record 3\n"
```

### Paso 4: Leer el archivo completo

```bash
# Leer todo el contenido
python3 mini_gfs/run_client.py read /demo.txt 0 100
```

### Paso 5: Simular fallo y re-replicación

1. Detener uno de los ChunkServers (Ctrl+C en su terminal)
2. Esperar unos segundos para que el Master detecte el fallo
3. El Master debería detectar chunks que necesitan re-replicación
4. Continuar leyendo/escribiendo - el sistema debería seguir funcionando

```bash
# El sistema debería seguir funcionando con los ChunkServers restantes
python3 mini_gfs/run_client.py read /demo.txt 0 100
python3 mini_gfs/run_client.py append /demo.txt "Record después del fallo\n"
```

## Configuración

Los archivos de configuración están en `configs/`:

- `configs/master.yaml`: Configuración del Master
- `configs/chunkserver.yaml`: Configuración base de ChunkServers

### Parámetros importantes:

- `chunk_size`: Tamaño de cada chunk (por defecto 64 MB, como en GFS original)
- `replication_factor`: Número de réplicas por chunk (por defecto 3)
- `heartbeat_timeout`: Tiempo antes de considerar un ChunkServer muerto (segundos)
- `lease_duration`: Duración de los leases (segundos)
- `wal_dir`: Directorio donde se guarda el Write-Ahead Log (por defecto `data/master`)
- `wal_file`: Nombre del archivo WAL (por defecto `wal.log`)

### Configuración de ChunkServer:

- `rack_id`: ID del rack donde está ubicado el ChunkServer (por defecto "default")

## Arquitectura

### Master

- Mantiene metadatos en memoria:
  - Namespace de archivos (path -> FileMetadata)
  - Mapeo de chunks (chunk_handle -> ChunkMetadata) con versionado
  - Información de ChunkServers con awareness de racks
  - Leases activos
- Persiste metadatos periódicamente a disco (JSON snapshot)
- Coordina operaciones de archivos
- Gestiona réplicas y leases con versionado
- Detecta fallos y coordina re-replicación
- **Garbage collection**: Identifica y elimina chunks huérfanos automáticamente
- **Servidor HTTP con threading**: Maneja peticiones concurrentes usando `ThreadingTCPServer`
- **Background worker**: Thread separado para tareas periódicas (detección de fallos, re-replicación, snapshots, garbage collection)
- **Sincronización**: Usa `RLock` (reentrant lock) para permitir llamadas anidadas seguras

### ChunkServer

- Almacena chunks en disco local (un archivo por chunk: `<chunk_handle>.chunk`)
- **Checksums de integridad**: Mantiene checksums de 32 bits por bloques de 64KB
- Verifica checksums en cada lectura para detectar corrupción
- Se registra con el Master al iniciar (incluye `rack_id`)
- Envía heartbeats periódicos al Master (cada 10 segundos por defecto)
- Responde a peticiones de lectura/escritura
- Soporta data pipeline para escrituras eficientes
- Puede clonar chunks desde otros ChunkServers para re-replicación
- Puede eliminar chunks localmente cuando se marcan como garbage
- **Servidor HTTP con threading**: Maneja múltiples peticiones concurrentes
- **Thread de heartbeat**: Envía heartbeats periódicos sin bloquear el servidor principal

### Cliente

- Se comunica con el Master para metadatos
- Se comunica con ChunkServers para datos
- **Data pipeline**: Envía datos en cadena (Cliente → Réplica1 → Réplica2 → Réplica3) para eficiencia
- Lee de cualquier réplica disponible (con verificación de checksums)
- **Asignación automática de chunks**: Si un archivo no tiene chunks, los asigna automáticamente al escribir
- Soporta operaciones de namespace: snapshot, rename, delete, list

## API HTTP

### Master API

- `POST /register_chunkserver`: Registro de ChunkServer (incluye `rack_id`)
- `POST /heartbeat`: Heartbeat de ChunkServer
- `POST /create_file`: Crear archivo
- `POST /get_file_info`: Obtener información de archivo
- `POST /allocate_chunk`: Asignar nuevo chunk
- `POST /get_chunk_locations`: Obtener ubicaciones de chunk
- `POST /snapshot_file`: Crear snapshot de archivo
- `POST /rename_file`: Renombrar archivo
- `POST /delete_file`: Eliminar archivo
- `POST /list_directory`: Listar archivos en directorio

### ChunkServer API

- `POST /write_chunk`: Escribir en chunk
- `POST /write_chunk_pipeline`: Escribir en chunk desde pipeline (otro ChunkServer)
- `POST /read_chunk`: Leer de chunk (con verificación de checksums)
- `POST /append_record`: Añadir record al final
- `POST /clone_chunk`: Clonar chunk desde otro ChunkServer
- `POST /delete_chunk`: Eliminar chunk localmente

## Testing

El proyecto incluye tests unitarios básicos para verificar la funcionalidad del sistema:

```bash
# Ejecutar tests
python3 -m pytest tests/
# o
python3 -m unittest discover tests
```

Los tests actuales cubren:
- Creación de archivos
- Asignación de chunks
- Persistencia y carga de snapshots de metadatos

## Limitaciones y Simplificaciones

Este es un proyecto educativo, no un sistema de producción. Las siguientes simplificaciones se aplican:

### Simplificaciones intencionales (para hacer el proyecto más útil y educativo):

- **Write-Ahead Log (WAL) implementado**: El Master registra todas las operaciones de mutación en un log antes de aplicarlas, permitiendo recuperación ante fallos. Similar al GFS real.
- **Recuperación desde WAL**: El sistema puede recuperar el estado completo desde el log de operaciones, incluso si el snapshot está desactualizado.
- **Snapshots periódicos**: El Master guarda snapshots periódicos de metadatos para recuperación rápida.
- **Re-replicación automática**: Cuando un ChunkServer falla, el sistema detecta chunks con réplicas insuficientes y los re-replica automáticamente.
- **Leases con primary chunkserver**: Implementación completa del sistema de leases para coordinar escrituras.
- **Record append atómico**: Operación atómica para añadir records al final de archivos, similar a GFS.

### Limitaciones (no implementadas por simplicidad):

- No hay ACLs jerárquicos (control de acceso)
- No hay replicación del Master (shadow masters) - single point of failure
  - *Nota: Los shadow masters son una extensión avanzada que requiere sincronización compleja del WAL*
- La re-replicación es síncrona y simplificada (no hay pipeline de datos en re-replicación)
- No hay compresión de datos
- No hay streaming optimizado para archivos muy grandes
- El sistema de versiones no se sincroniza completamente con ChunkServers (simplificado)

## Detalles de Implementación

### Concurrencia y Threading

- **Master y ChunkServers**: Usan `socketserver.ThreadingTCPServer` para manejar múltiples peticiones HTTP concurrentes
- **Locks**: El Master usa `threading.RLock` (reentrant lock) para sincronización segura de metadatos
- **Background threads**: 
  - Master tiene un thread de background para detección de fallos y re-replicación
  - ChunkServers tienen threads de background para enviar heartbeats periódicos

### Protocolo de Comunicación

- Todas las comunicaciones usan HTTP con JSON
- Los datos binarios se codifican en base64 para transmisión JSON
- Timeouts configurables para evitar bloqueos indefinidos

### Persistencia

- **Write-Ahead Log (WAL)**: El Master registra todas las operaciones de mutación en `data/master/wal.log` antes de aplicarlas a los metadatos en memoria. Esto permite:
  - Recuperación completa del estado desde el log
  - Durabilidad de las operaciones (fsync después de cada escritura)
  - Replay de operaciones después de un fallo
  
- **Snapshots periódicos**: El Master guarda snapshots periódicos de metadatos en `data/master/metadata_snapshot.json` para recuperación rápida. Los snapshots se combinan con el WAL para recuperación completa.

- **Almacenamiento de chunks**: Los chunks se almacenan como archivos individuales en disco en cada ChunkServer (`<chunk_handle>.chunk`)

- **Recuperación**: Al iniciar, el Master:
  1. Carga el snapshot más reciente (si existe)
  2. Reproduce todas las operaciones del WAL para aplicar cambios posteriores al snapshot
  3. Esto garantiza que no se pierdan operaciones incluso si el snapshot está desactualizado

## Referencias

### Paper Original

- **Ghemawat, S., Gobioff, H., & Leung, S. T. (2003).** The Google file system. ACM SIGOPS operating systems review, 37(5), 29-43.

### Paper Completo

El paper completo del Google File System está disponible en este repositorio:

- **[The Google File System.pdf](The%20Google%20File%20System.pdf)** - Paper completo presentado en SOSP 2003

Este documento describe en detalle:
- La arquitectura y diseño de GFS
- Las decisiones de diseño y sus justificaciones
- El protocolo de replicación y consistencia
- Los mecanismos de recuperación ante fallos
- Evaluación de rendimiento y casos de uso en Google

Se recomienda leer este paper para entender completamente los conceptos implementados en este mini-GFS educativo.

## Licencia

Este proyecto es educativo y está destinado a fines de aprendizaje.

