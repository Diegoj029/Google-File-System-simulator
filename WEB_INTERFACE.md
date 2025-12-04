# Interfaz Web del Mini-GFS

## Introducción

La interfaz web del Mini-GFS es una herramienta gráfica e interactiva diseñada especialmente para fines educativos. Permite gestionar y visualizar el sistema GFS completo desde un navegador web, con visualizaciones didácticas que ayudan a entender cómo funciona el sistema de archivos distribuido.

### Características Principales

- **Gestión Automática del Sistema**: Inicia y detiene automáticamente Master + 3 ChunkServers
- **Gestión Dinámica de ChunkServers**: Agregar, quitar y restaurar ChunkServers sin reiniciar el sistema
- **Visualización de Topología de Red**: Muestra la arquitectura del sistema de forma clara y educativa
- **Distribución de Chunks**: Visualiza cómo se distribuyen los chunks entre ChunkServers
- **Gestión Completa de Archivos**: Crear, leer, escribir, añadir, renombrar, crear snapshots y eliminar archivos directamente desde la interfaz
- **Métricas Avanzadas en Tiempo Real**: Monitoreo completo del sistema incluyendo throughput, latencia, tasa de fallos y más
- **Gráficas de Rendimiento**: Visualización de métricas históricas
- **Configuración Dinámica**: Modificar parámetros del sistema en tiempo real

## Instalación

### Requisitos

- Python 3.11 o superior
- Dependencias: `requests`, `pyyaml`, `matplotlib`, `networkx`

### Instalación de Dependencias

```bash
pip install -r requirements.txt
```

O instalar manualmente:

```bash
pip install requests pyyaml matplotlib networkx
```

## Uso

### Ejecutar la Interfaz Web

```bash
python3 mini_gfs/run_web.py
```

La interfaz estará disponible en: **http://localhost:8080**

Abre tu navegador y navega a esa dirección.

### Inicio Automático

Al ejecutar `run_web.py`, la interfaz web se inicia pero **no inicia automáticamente** el sistema GFS. Debes hacer clic en el botón "▶️ Iniciar Sistema" para que se levanten el Master y los 3 ChunkServers.

## Funcionalidades

### 1. Panel de Control del Sistema

Este panel permite gestionar los procesos del sistema:

- **Iniciar Sistema**: Inicia automáticamente el Master y 3 ChunkServers
- **Detener Sistema**: Detiene todos los procesos
- **Actualizar Estado**: Refresca el estado de los procesos
- **Agregar ChunkServer**: Permite agregar dinámicamente nuevos ChunkServers al sistema (el puerto se asigna automáticamente)
- **Quitar ChunkServer**: Detiene temporalmente un ChunkServer específico sin eliminarlo permanentemente
- **Restaurar ChunkServer**: Restaura un ChunkServer que fue quitado previamente, manteniendo su configuración original

**Indicadores de Estado**:
- ● Verde: Proceso ejecutándose
- ● Rojo: Proceso detenido

Cada proceso muestra su PID (Process ID) y puerto cuando está ejecutándose. Los ChunkServers quitados pueden ser restaurados posteriormente manteniendo su configuración original.

**Gestión Dinámica de ChunkServers**:
- Puedes agregar ChunkServers adicionales en tiempo real para escalar el sistema
- Los ChunkServers quitados se marcan como detenidos y pueden ser restaurados
- Al restaurar un ChunkServer, este se vuelve a registrar con el Master y recupera su estado

### 2. Panel de Visualización de Red

Este es uno de los paneles más importantes y didácticos de la interfaz.

#### ¿Qué muestra?

La topología de red muestra:
- **Master**: El coordinador central (nodo azul grande en el centro)
- **ChunkServers**: Los servidores que almacenan datos (nodos alrededor del Master)
- **Conexiones**: Líneas que representan la comunicación entre componentes

#### Elementos Visuales

- **Master (Azul)**: Coordinador central que gestiona todos los metadatos
- **ChunkServer Vivo (Verde)**: ChunkServer activo y respondiendo
- **ChunkServer Muerto (Rojo)**: ChunkServer que no responde o está detenido
- **Conexiones (Gris)**: Representan heartbeats y comunicación de registro

#### Información Educativa

**¿Qué es el Master?**
El Master es el coordinador central del sistema GFS. Mantiene todos los metadatos (información sobre archivos, chunks, y dónde están almacenados) en memoria. No almacena datos reales, solo información sobre dónde encontrarlos.

**¿Qué son los ChunkServers?**
Los ChunkServers son los servidores que realmente almacenan los datos (chunks) en disco. Cada ChunkServer almacena múltiples chunks y se comunica periódicamente con el Master mediante "heartbeats" para reportar su estado.

**¿Qué son las conexiones?**
Las conexiones representan la comunicación entre el Master y cada ChunkServer. Incluyen:
- **Registro**: Cuando un ChunkServer se inicia, se registra con el Master
- **Heartbeats**: Mensajes periódicos que indican que el ChunkServer está vivo
- **Comandos**: Instrucciones del Master a los ChunkServers

#### Interactividad

- **Hover**: Pasa el mouse sobre un nodo para ver información detallada
- **Actualización Automática**: La topología se actualiza cada 3 segundos
- **Botón Actualizar**: Puedes actualizar manualmente haciendo clic en "🔄 Actualizar Topología"

### 3. Panel de Distribución de Chunks

Este panel muestra cómo se distribuyen los chunks (porciones de archivos) entre los ChunkServers.

#### ¿Qué es un Chunk?

Un chunk es una porción de un archivo. En este simulador, cada chunk tiene un tamaño de 1 MB (configurable). Los archivos grandes se dividen en múltiples chunks.

#### ¿Cómo funciona la Replicación?

Cada chunk se replica en múltiples ChunkServers para tolerancia a fallos. Por defecto, cada chunk tiene 3 réplicas (replication_factor = 3). Esto significa que:
- Si un ChunkServer falla, el archivo sigue siendo accesible desde las otras réplicas
- El sistema puede re-replicar automáticamente chunks que quedan con menos réplicas de las requeridas

#### Vistas Disponibles

**Vista General**:
- **Gráfico de Barras**: Muestra cuántos chunks tiene cada ChunkServer
- **Tabla Detallada**: Lista todos los chunks con información completa
  - Chunk Handle (identificador único)
  - Archivo al que pertenece
  - ChunkServers donde está replicado
  - Tamaño y versión
  - Estado de replicación (Completo o Sub-replicado)
- **Gráfico de Red**: Visualización tipo grafo mostrando chunks y sus réplicas

**Vista por Archivo**:
- **Diagrama Visual**: Muestra los chunks de un archivo específico
- **Réplicas**: Visualiza en qué ChunkServers está cada chunk
- **Tabla de Chunks**: Información detallada de cada chunk del archivo

#### Colores y Estados

- **Verde**: Chunk con réplicas completas (tiene todas las réplicas requeridas)
- **Amarillo**: Chunk sub-replicado (tiene menos réplicas de las requeridas)
- **Rojo**: Chunk crítico (muy pocas réplicas, riesgo de pérdida de datos)

#### Información Educativa

**¿Qué significa "sub-replicado"?**
Un chunk está sub-replicado cuando tiene menos réplicas de las requeridas por el `replication_factor`. Por ejemplo, si el replication_factor es 3 y un chunk solo tiene 2 réplicas, está sub-replicado.

**¿Qué pasa si un ChunkServer falla?**
Cuando un ChunkServer falla:
1. El Master detecta el fallo mediante heartbeats
2. Identifica chunks que ahora tienen menos réplicas
3. Inicia automáticamente la re-replicación desde las réplicas restantes
4. El sistema continúa funcionando normalmente

**¿Cómo se distribuyen los chunks?**
El Master distribuye los chunks entre ChunkServers considerando:
- Balanceo de carga (distribuir uniformemente)
- Awareness de racks (preferir racks diferentes para tolerancia a fallos)
- Disponibilidad de espacio

### 4. Panel de Archivos

Este panel permite realizar todas las operaciones de archivos directamente desde la interfaz web. El panel está dividido en dos secciones: operaciones y lista de archivos.

#### Operaciones Disponibles

**Operaciones Básicas**:
- **Crear Archivo**: Crea un nuevo archivo vacío en el sistema
- **Listar Archivos**: Muestra todos los archivos en el sistema con acceso rápido a operaciones

**Operaciones de Lectura y Escritura**:
- **Escribir en Archivo**: Escribe contenido en un archivo desde un offset específico (en bytes)
- **Leer Archivo**: Lee contenido de un archivo desde un offset específico, mostrando el resultado directamente en la interfaz
- **Añadir al Final (Append)**: Añade contenido al final del archivo usando la operación record append atómica

**Operaciones de Gestión**:
- **Ver Información (ls)**: Muestra información detallada de un archivo, incluyendo:
  - Número de chunks
  - Chunk handles
  - Réplicas y ChunkServers donde están almacenadas
  - ChunkServer primary para cada chunk
  - Tamaño de cada chunk
- **Renombrar Archivo**: Cambia el nombre/ruta de un archivo
- **Crear Snapshot**: Crea una copia instantánea de un archivo usando copy-on-write
- **Eliminar Archivo**: Elimina un archivo del sistema

#### Operaciones Rápidas

Desde la lista de archivos puedes:
- Ver el contenido completo de un archivo haciendo clic en "Leer"
- Ver la información detallada haciendo clic en "Info"
- Eliminar un archivo directamente desde la lista

**Nota**: Todas las operaciones de archivos están disponibles desde la interfaz web. El CLI (`run_client.py`) sigue disponible para scripts automatizados o uso en línea de comandos.

### 5. Panel de Configuración

Permite modificar parámetros del sistema:

- **Replication Factor**: Número de réplicas por chunk (1-5)
- **Chunk Size**: Tamaño de cada chunk en MB
- **Heartbeat Timeout**: Tiempo antes de considerar un ChunkServer muerto (segundos)
- **Lease Duration**: Duración del lease para escrituras (segundos)

**Nota**: La actualización de configuración requiere reiniciar el sistema para que los cambios surtan efecto.

### 6. Panel de Métricas

Muestra métricas en tiempo real del sistema actualizándose automáticamente cada 5 segundos.

#### Métricas Básicas

- **ChunkServers Vivos**: Número de ChunkServers activos y respondiendo
- **ChunkServers Muertos**: Número de ChunkServers inactivos o no respondiendo
- **Total de Chunks**: Número total de chunks en el sistema
- **Chunks Sub-replicados**: Chunks que tienen menos réplicas de las requeridas
- **Total de Archivos**: Número de archivos en el sistema

#### Métricas de Rendimiento

- **Throughput (ops/s)**: Total de operaciones por segundo (suma de lecturas, escrituras y appends)
- **Latencia Promedio (ms)**: Tiempo promedio de respuesta de las operaciones
- **Latencia P95 (ms)**: Percentil 95 de latencia (95% de las operaciones son más rápidas)
- **Latencia P99 (ms)**: Percentil 99 de latencia (99% de las operaciones son más rápidas)

#### Métricas de Confiabilidad

- **Tasa de Fallos (fallos/hora)**: Frecuencia de fallos en el sistema
- **Re-replicaciones Activas**: Número de operaciones de re-replicación en curso
- **Réplicas Obsoletas**: Número de réplicas que están desactualizadas (versiones antiguas)

#### Detalles Adicionales

El panel muestra información detallada expandible que incluye:
- **Throughput por Tipo de Operación**: Desglose de lecturas, escrituras y appends
- **Latencia por Tipo de Operación**: Métricas de latencia separadas por tipo de operación (read, write, append)
- **Carga por ChunkServer**: Distribución de operaciones y bytes transferidos por cada ChunkServer
- **Fragmentación de Archivos**: Estadísticas sobre la distribución de chunks en archivos
- **Réplicas Obsoletas Detalladas**: Información sobre chunks que tienen réplicas obsoletas

Las métricas se actualizan automáticamente cada 5 segundos, o puedes actualizar manualmente usando el botón "🔄 Actualizar Métricas".

### 7. Panel de Gráficas

Genera gráficas visuales del sistema:

- **Gráfica de Rendimiento**: Muestra métricas históricas (ChunkServers vivos, total de chunks, chunks sub-replicados)
- **Vista del Cluster**: Visualización de la distribución de chunks y estado de réplicas
- **Topología de Red**: Imagen estática de la topología
- **Distribución de Chunks**: Imagen estática de la distribución

Las gráficas se generan como imágenes PNG y se muestran en el panel.

## Guía Didáctica

### Ejercicio 1: Explorar la Topología

1. Inicia el sistema desde la interfaz web
2. Observa la topología de red
3. Identifica el Master y los 3 ChunkServers
4. Verifica que todos los ChunkServers estén "vivos" (verde)

**Preguntas para reflexionar**:
- ¿Por qué el Master está en el centro?
- ¿Qué pasaría si el Master falla?
- ¿Cómo se comunican los componentes?

### Ejercicio 2: Crear Archivos y Ver Distribución

1. Crea un archivo desde la interfaz: `/mi_archivo.txt`
2. Escribe contenido desde la interfaz web usando la operación "Escribir"
   - Ruta: `/mi_archivo.txt`
   - Offset: `0`
   - Contenido: `"Contenido de prueba"`
3. Actualiza la distribución de chunks
4. Observa cómo se distribuyen los chunks entre ChunkServers
5. Usa "Añadir" para agregar más contenido al archivo
6. Lee el archivo completo desde la interfaz para ver todo el contenido

**Preguntas para reflexionar**:
- ¿En cuántos ChunkServers está cada chunk?
- ¿Por qué se distribuyen así?
- ¿Qué pasa si un ChunkServer tiene más chunks que otro?
- ¿Cómo funciona la operación "append" comparada con "write"?

### Ejercicio 3: Simular un Fallo y Gestión Dinámica

1. Crea algunos archivos y escribe contenido
2. Observa la distribución de chunks
3. **Opción A**: Quita un ChunkServer desde la interfaz web usando el botón "🗑️ Quitar" en el Panel de Control
   **Opción B**: Detén manualmente uno de los ChunkServers (Ctrl+C en su terminal)
4. Espera unos segundos
5. Observa cómo cambia la topología (el ChunkServer se vuelve rojo)
6. Observa cómo cambian las métricas:
   - Chunks sub-replicados aumentan
   - Re-replicaciones activas se muestran en las métricas
   - La topología se actualiza automáticamente
7. El sistema debería iniciar re-replicación automáticamente
8. **(Nuevo)** Restaura el ChunkServer desde la interfaz usando "▶️ Restaurar"
9. Observa cómo el sistema vuelve a su estado normal

**Preguntas para reflexionar**:
- ¿Por qué el sistema sigue funcionando aunque un ChunkServer falle?
- ¿Cómo detecta el Master que un ChunkServer falló?
- ¿Qué significa "re-replicación"?
- ¿Qué ventajas tiene poder agregar y quitar ChunkServers dinámicamente?

### Ejercicio 4: Cambiar Replication Factor

1. Cambia el replication_factor a 2 en el panel de configuración
2. Crea un nuevo archivo
3. Observa la distribución de chunks
4. Compara con archivos creados con replication_factor = 3

**Preguntas para reflexionar**:
- ¿Cuál es el trade-off entre más réplicas y menos réplicas?
- ¿Cuántas réplicas necesitas para tolerar 1 fallo? ¿Y 2 fallos?

### Ejercicio 5: Operaciones Avanzadas de Archivos

1. Crea un archivo `/test.txt` y escribe contenido en él
2. Crea un snapshot del archivo: `/test.txt.snapshot`
3. Modifica el archivo original añadiendo más contenido
4. Lee ambos archivos para comparar:
   - El archivo original debería tener el contenido nuevo
   - El snapshot debería tener el contenido original (copy-on-write)
5. Renombra el archivo original a `/test_renamed.txt`
6. Observa cómo se actualiza la lista de archivos
7. Usa "Ver Información" para explorar los chunks de cada archivo

**Preguntas para reflexionar**:
- ¿Cómo funciona copy-on-write en los snapshots?
- ¿Qué ventajas tiene la operación "append" sobre "write"?
- ¿Cómo se gestionan los chunks cuando renombramos un archivo?

### Ejercicio 6: Explorar Métricas Avanzadas

1. Realiza varias operaciones de lectura y escritura desde la interfaz
2. Observa las métricas en tiempo real:
   - Throughput: operaciones por segundo
   - Latencia: tiempos de respuesta promedio, P95, P99
3. Agrega o quita un ChunkServer y observa cómo cambian las métricas
4. Expande los "Detalles Adicionales" en el panel de métricas
5. Observa:
   - Throughput por tipo de operación (read, write, append)
   - Latencia desglosada por operación
   - Carga por ChunkServer
   - Fragmentación de archivos
   - Réplicas obsoletas

**Preguntas para reflexionar**:
- ¿Qué tipo de operación es más rápida: read, write o append?
- ¿Cómo se distribuye la carga entre ChunkServers?
- ¿Qué significa el percentil 95 (P95) de latencia?

### Ejercicio 7: Escalado Dinámico

1. Inicia el sistema con 3 ChunkServers por defecto
2. Crea varios archivos con contenido
3. Observa la distribución inicial de chunks
4. Agrega un cuarto ChunkServer desde la interfaz
5. Crea nuevos archivos y observa cómo se distribuyen entre los 4 ChunkServers
6. Observa la topología actualizada automáticamente
7. Quita uno de los ChunkServers
8. Observa cómo el sistema re-replica los chunks automáticamente
9. Restaura el ChunkServer que quitaste

**Preguntas para reflexionar**:
- ¿Cómo se balancea la carga cuando agregas más ChunkServers?
- ¿Qué sucede con los chunks existentes cuando escalas el sistema?
- ¿Por qué es importante poder escalar dinámicamente?

## API Endpoints

La interfaz web expone una API REST en `/api/`:

### Sistema
- `GET /api/system/status` - Estado del sistema (Master y ChunkServers)
- `GET /api/system/topology` - Topología de red
- `POST /api/system/start` - Iniciar sistema (Master + 3 ChunkServers)
- `POST /api/system/stop` - Detener sistema

### ChunkServers
- `POST /api/chunkservers/add` - Agregar un nuevo ChunkServer (puerto automático)
- `POST /api/chunkservers/remove` - Quitar un ChunkServer (parámetro: `chunkserver_id`)
- `POST /api/chunkservers/restore` - Restaurar un ChunkServer previamente quitado
- `GET /api/chunkservers/list` - Listar información de todos los ChunkServers

### Archivos
- `GET /api/files/list` - Listar archivos en el sistema
- `GET /api/files/info?path=...` - Información detallada de un archivo
- `POST /api/files/create` - Crear archivo (parámetro: `path`)
- `POST /api/files/write` - Escribir en archivo (parámetros: `path`, `offset`, `content`)
- `POST /api/files/read` - Leer archivo (parámetros: `path`, `offset`, `length` opcional)
- `POST /api/files/append` - Añadir al final del archivo (parámetros: `path`, `content`)
- `POST /api/files/snapshot` - Crear snapshot (parámetros: `source_path`, `dest_path`)
- `POST /api/files/rename` - Renombrar archivo (parámetros: `old_path`, `new_path`)
- `POST /api/files/delete` - Eliminar archivo (parámetro: `path`)

### Chunks
- `GET /api/chunks/distribution?file_path=...` - Distribución de chunks (opcional: filtro por archivo)

### Configuración
- `GET /api/config/get` - Obtener configuración actual
- `POST /api/config/update` - Actualizar configuración (parámetros: `replication_factor`, `chunk_size`, `heartbeat_timeout`, `lease_duration`)

### Métricas
- `GET /api/metrics/current` - Métricas actuales del sistema
- `GET /api/metrics/history?limit=...` - Historial de métricas (opcional: límite de entradas)
- `POST /api/metrics/graph` - Generar gráfica de rendimiento

### Visualizaciones
- `POST /api/visualization/topology` - Generar imagen estática de la topología
- `POST /api/visualization/distribution` - Generar imagen de distribución (opcional: `file_path` para filtrar)
- `POST /api/visualization/cluster` - Generar vista del cluster

## Troubleshooting

### El sistema no inicia

- Verifica que los puertos 8000, 8001, 8002, 8003 no estén en uso
- Revisa los logs en la consola donde ejecutaste `run_web.py`
- Asegúrate de que todas las dependencias estén instaladas

### La topología no se muestra

- Verifica que el Master esté ejecutándose
- Asegúrate de que los ChunkServers estén registrados
- Revisa la consola del navegador (F12) para errores JavaScript

### Las visualizaciones no se generan

- Verifica que matplotlib esté instalado: `pip install matplotlib networkx`
- Revisa que el directorio `output/` exista y tenga permisos de escritura

### Los archivos no aparecen

- Asegúrate de haber creado archivos usando el CLI o la interfaz
- Verifica que el Master esté ejecutándose
- Actualiza la lista de archivos manualmente

## Arquitectura Técnica

### Componentes

- **ProcessManager**: Gestiona procesos (Master y ChunkServers)
- **MetricsCollector**: Recolecta métricas del sistema
- **VisualizationGenerator**: Genera gráficas con matplotlib
- **WebServer**: Servidor HTTP que sirve la interfaz y expone la API

### Tecnologías

- **Backend**: Python 3.11+, HTTP/JSON, Threading
- **Frontend**: HTML5, CSS3, JavaScript (ES6+), D3.js
- **Visualización**: Matplotlib, NetworkX, D3.js

## Notas Finales

Esta interfaz web está diseñada específicamente para fines educativos. Las visualizaciones priorizan la claridad y la explicación sobre la complejidad visual. El objetivo es ayudar a entender cómo funciona GFS de forma visual e interactiva.

Para operaciones avanzadas o scripts automatizados, sigue usando el CLI (`run_client.py`).

Esta guía se realizó con ayuda de ChatGPT 5.1, puede contener errores.

