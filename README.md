# Mini Google File System (GFS)

Un sistema de archivos distribuido educativo inspirado en el Google File System (Ghemawat et al., SOSP 2003).

Este es un proyecto educativo que implementa los conceptos principales de GFS de forma simplificada:
- Un Master central que mantiene metadatos en memoria
- Múltiples ChunkServers que almacenan chunks en disco local
- Un Cliente CLI para operaciones de archivos
- Replicación, leases con primary chunkserver para escrituras, y record append simplificado

## Características

- **Master único**: Coordina todas las operaciones y mantiene metadatos en memoria
- **ChunkServers múltiples**: Almacenan chunks replicados en disco local
- **Replicación**: Cada chunk se replica en múltiples ChunkServers (por defecto 3)
- **Leases**: El Master otorga leases a un ChunkServer para actuar como primary
- **Record Append**: Operación atómica para añadir records al final de archivos
- **Detección de fallos**: El Master detecta ChunkServers muertos mediante heartbeats
- **Re-replicación**: Automática cuando un chunk tiene menos réplicas de las requeridas

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

- `chunk_size`: Tamaño de cada chunk (por defecto 1 MB)
- `replication_factor`: Número de réplicas por chunk (por defecto 3)
- `heartbeat_timeout`: Tiempo antes de considerar un ChunkServer muerto (segundos)
- `lease_duration`: Duración de los leases (segundos)

## Arquitectura

### Master

- Mantiene metadatos en memoria:
  - Namespace de archivos (path -> FileMetadata)
  - Mapeo de chunks (chunk_handle -> ChunkMetadata)
  - Información de ChunkServers
  - Leases activos
- Persiste metadatos periódicamente a disco (JSON snapshot)
- Coordina operaciones de archivos
- Gestiona réplicas y leases
- Detecta fallos y coordina re-replicación
- **Servidor HTTP con threading**: Maneja peticiones concurrentes usando `ThreadingTCPServer`
- **Background worker**: Thread separado para tareas periódicas (detección de fallos, re-replicación, snapshots)
- **Sincronización**: Usa `RLock` (reentrant lock) para permitir llamadas anidadas seguras

### ChunkServer

- Almacena chunks en disco local (un archivo por chunk: `<chunk_handle>.chunk`)
- Se registra con el Master al iniciar
- Envía heartbeats periódicos al Master (cada 10 segundos por defecto)
- Responde a peticiones de lectura/escritura
- Puede clonar chunks desde otros ChunkServers para re-replicación
- **Servidor HTTP con threading**: Maneja múltiples peticiones concurrentes
- **Thread de heartbeat**: Envía heartbeats periódicos sin bloquear el servidor principal

### Cliente

- Se comunica con el Master para metadatos
- Se comunica con ChunkServers para datos
- Coordina operaciones de escritura (data push a todas las réplicas)
- Lee de cualquier réplica disponible
- **Asignación automática de chunks**: Si un archivo no tiene chunks, los asigna automáticamente al escribir

## API HTTP

### Master API

- `POST /register_chunkserver`: Registro de ChunkServer
- `POST /heartbeat`: Heartbeat de ChunkServer
- `POST /create_file`: Crear archivo
- `POST /get_file_info`: Obtener información de archivo
- `POST /allocate_chunk`: Asignar nuevo chunk
- `POST /get_chunk_locations`: Obtener ubicaciones de chunk

### ChunkServer API

- `POST /write_chunk`: Escribir en chunk
- `POST /read_chunk`: Leer de chunk
- `POST /append_record`: Añadir record al final
- `POST /clone_chunk`: Clonar chunk desde otro ChunkServer

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

- No hay snapshots de archivos
- No hay renombrado de archivos
- No hay ACLs jerárquicos
- No hay checksums ni verificación de integridad
- No hay awareness de racks
- No hay garbage collection distribuido
- La persistencia de metadatos es un simple JSON (no logs de operaciones)
- La re-replicación es síncrona y simplificada
- El tamaño de chunk es fijo (1 MB por defecto, no 64 MB como en GFS real)
- No hay optimizaciones de red (data pipeline simplificado)

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

- El Master guarda snapshots periódicos de metadatos en `data/master/metadata_snapshot.json`
- Los chunks se almacenan como archivos individuales en disco
- No hay logs de operaciones (WAL) - solo snapshots periódicos

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

