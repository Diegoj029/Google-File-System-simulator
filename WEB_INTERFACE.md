# Interfaz Web del Mini-GFS

## Introducción

La interfaz web del Mini-GFS es una herramienta gráfica e interactiva diseñada especialmente para fines educativos. Permite gestionar y visualizar el sistema GFS completo desde un navegador web, con visualizaciones didácticas que ayudan a entender cómo funciona el sistema de archivos distribuido.

### Características Principales

- **Gestión Automática del Sistema**: Inicia y detiene automáticamente Master + 3 ChunkServers
- **Visualización de Topología de Red**: Muestra la arquitectura del sistema de forma clara y educativa
- **Distribución de Chunks**: Visualiza cómo se distribuyen los chunks entre ChunkServers
- **Gestión de Archivos**: Crear, leer, explorar y eliminar archivos desde la interfaz
- **Métricas en Tiempo Real**: Monitoreo del estado del sistema
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

**Indicadores de Estado**:
- ● Verde: Proceso ejecutándose
- ● Rojo: Proceso detenido

Cada proceso muestra su PID (Process ID) cuando está ejecutándose.

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

Permite gestionar archivos en el sistema:

- **Listar Archivos**: Ver todos los archivos en el sistema
- **Crear Archivo**: Crear un nuevo archivo (solo crea el archivo vacío, para escribir contenido usa el CLI)
- **Ver Información**: Ver detalles de un archivo (chunks, réplicas, etc.)
- **Eliminar Archivo**: Eliminar un archivo del sistema

**Nota**: Para escribir y leer contenido de archivos, usa el CLI (`run_client.py`). La interfaz web permite crear y gestionar archivos, pero las operaciones de lectura/escritura de contenido requieren el cliente.

### 5. Panel de Configuración

Permite modificar parámetros del sistema:

- **Replication Factor**: Número de réplicas por chunk (1-5)
- **Chunk Size**: Tamaño de cada chunk en MB
- **Heartbeat Timeout**: Tiempo antes de considerar un ChunkServer muerto (segundos)
- **Lease Duration**: Duración del lease para escrituras (segundos)

**Nota**: La actualización de configuración requiere reiniciar el sistema para que los cambios surtan efecto.

### 6. Panel de Métricas

Muestra métricas en tiempo real del sistema:

- **ChunkServers Vivos**: Número de ChunkServers activos
- **ChunkServers Muertos**: Número de ChunkServers inactivos
- **Total de Chunks**: Número total de chunks en el sistema
- **Chunks Sub-replicados**: Chunks que necesitan re-replicación
- **Total de Archivos**: Número de archivos en el sistema

Las métricas se actualizan automáticamente cada 5 segundos.

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
2. Usa el CLI para escribir contenido:
   ```bash
   python3 mini_gfs/run_client.py write /mi_archivo.txt 0 "Contenido de prueba"
   ```
3. Vuelve a la interfaz y actualiza la distribución de chunks
4. Observa cómo se distribuyen los chunks entre ChunkServers

**Preguntas para reflexionar**:
- ¿En cuántos ChunkServers está cada chunk?
- ¿Por qué se distribuyen así?
- ¿Qué pasa si un ChunkServer tiene más chunks que otro?

### Ejercicio 3: Simular un Fallo

1. Crea algunos archivos y escribe contenido
2. Observa la distribución de chunks
3. Detén manualmente uno de los ChunkServers (Ctrl+C en su terminal)
4. Espera unos segundos
5. Observa cómo cambia la topología (el ChunkServer se vuelve rojo)
6. Observa cómo cambian las métricas (chunks sub-replicados aumentan)
7. El sistema debería iniciar re-replicación automáticamente

**Preguntas para reflexionar**:
- ¿Por qué el sistema sigue funcionando aunque un ChunkServer falle?
- ¿Cómo detecta el Master que un ChunkServer falló?
- ¿Qué significa "re-replicación"?

### Ejercicio 4: Cambiar Replication Factor

1. Cambia el replication_factor a 2 en el panel de configuración
2. Crea un nuevo archivo
3. Observa la distribución de chunks
4. Compara con archivos creados con replication_factor = 3

**Preguntas para reflexionar**:
- ¿Cuál es el trade-off entre más réplicas y menos réplicas?
- ¿Cuántas réplicas necesitas para tolerar 1 fallo? ¿Y 2 fallos?

## API Endpoints

La interfaz web expone una API REST en `/api/`:

### Sistema
- `GET /api/system/status` - Estado del sistema
- `GET /api/system/topology` - Topología de red
- `POST /api/system/start` - Iniciar sistema
- `POST /api/system/stop` - Detener sistema

### Archivos
- `GET /api/files/list` - Listar archivos
- `GET /api/files/info?path=...` - Información de archivo
- `POST /api/files/create` - Crear archivo
- `POST /api/files/delete` - Eliminar archivo

### Chunks
- `GET /api/chunks/distribution?file_path=...` - Distribución de chunks

### Configuración
- `GET /api/config/get` - Obtener configuración
- `POST /api/config/update` - Actualizar configuración

### Métricas
- `GET /api/metrics/current` - Métricas actuales
- `GET /api/metrics/history?limit=...` - Historial de métricas
- `POST /api/metrics/graph` - Generar gráfica de rendimiento

### Visualizaciones
- `POST /api/visualization/topology` - Generar imagen de topología
- `POST /api/visualization/distribution` - Generar imagen de distribución
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

