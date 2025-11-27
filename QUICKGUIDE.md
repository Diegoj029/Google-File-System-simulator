# Guía Rápida: Mini Google File System (Simulador)

Esta guía contiene ejemplos prácticos y escenarios de prueba para mostrar la funcionalidad del simulador GFS.

## Tabla de Contenidos

1. [Configuración Inicial](#configuración-inicial)
2. [Operaciones Básicas](#operaciones-básicas)
3. [Operaciones Avanzadas](#operaciones-avanzadas)
4. [Escenarios de Prueba](#escenarios-de-prueba)
5. [Pruebas de Recuperación](#pruebas-de-recuperación)
6. [Pruebas de Concurrencia](#pruebas-de-concurrencia)
7. [Pruebas de Replicación](#pruebas-de-replicación)
8. [Verificación del WAL](#verificación-del-wal)
9. [Pruebas de Características Avanzadas](#pruebas-de-características-avanzadas)

---

## Configuración Inicial

### Paso 1: Iniciar el Sistema

Abre 4 terminales y ejecuta:

**Terminal 1 - Master:**
```bash
python3 mini_gfs/run_master.py
```

**Terminal 2 - ChunkServer 1 (Rack A):**
```bash
python3 mini_gfs/run_chunkserver.py --port 8001 --id cs1 --data-dir data/chunks/cs1
# Nota: Puedes configurar rack_id en configs/chunkserver.yaml
```

**Terminal 3 - ChunkServer 2 (Rack B):**
```bash
python3 mini_gfs/run_chunkserver.py --port 8002 --id cs2 --data-dir data/chunks/cs2
```

**Terminal 4 - ChunkServer 3 (Rack C):**
```bash
python3 mini_gfs/run_chunkserver.py --port 8003 --id cs3 --data-dir data/chunks/cs3
```

**Verificación:** Espera a ver mensajes de registro exitoso en el Master. Deberías ver algo como:
```
[Master] ChunkServer cs1 registrado
[Master] ChunkServer cs2 registrado
[Master] ChunkServer cs3 registrado
```

---

## Operaciones Básicas

### QA 1: Crear y Escribir un Archivo

**Objetivo:** Verificar creación de archivos y escritura básica.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /test1.txt

# Escribir datos
python3 mini_gfs/run_client.py write /test1.txt 0 "Hola, GFS!"

# Leer datos
python3 mini_gfs/run_client.py read /test1.txt 0 11

# Ver información del archivo
python3 mini_gfs/run_client.py ls /test1.txt
```

**Resultado esperado:**
- Archivo creado exitosamente
- Datos escritos correctamente
- Lectura devuelve "Hola, GFS!"
- `ls` muestra información del archivo con chunks asignados

---

### QA 2: Escritura en Múltiples Chunks

**Objetivo:** Verificar que el sistema maneja archivos que ocupan múltiples chunks.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /large.txt

# Escribir datos que excedan 1 MB (tamaño de chunk por defecto)
# Generar 1.5 MB de datos
python3 -c "
data = 'A' * (1024 * 1024) + 'B' * (512 * 1024)
with open('/tmp/large_data.txt', 'w') as f:
    f.write(data)
"

# Escribir en el archivo (necesitarás adaptar esto según tu implementación)
python3 mini_gfs/run_client.py write /large.txt 0 "$(cat /tmp/large_data.txt)"

# Ver información - debería mostrar múltiples chunks
python3 mini_gfs/run_client.py ls /large.txt
```

**Resultado esperado:**
- Archivo creado con múltiples chunks
- `ls` muestra lista de chunks con sus réplicas

---

### QA 3: Record Append (Operación Atómica)

**Objetivo:** Probar la operación de record append, característica clave de GFS.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /logs.txt

# Añadir múltiples records (simulando múltiples clientes escribiendo)
python3 mini_gfs/run_client.py append /logs.txt "Log entry 1\n"
python3 mini_gfs/run_client.py append /logs.txt "Log entry 2\n"
python3 mini_gfs/run_client.py append /logs.txt "Log entry 3\n"
python3 mini_gfs/run_client.py append /logs.txt "Log entry 4\n"

# Leer todo el contenido
python3 mini_gfs/run_client.py read /logs.txt 0 200
```

**Resultado esperado:**
- Todos los records se añaden correctamente
- Los records aparecen en orden (aunque pueden tener padding entre ellos)
- Lectura muestra todos los records concatenados

---

## Operaciones Avanzadas

### QA 17: Crear Snapshot de Archivo

**Objetivo:** Probar la funcionalidad de snapshot con copy-on-write.

```bash
# Crear archivo original
python3 mini_gfs/run_client.py create /original.txt
python3 mini_gfs/run_client.py write /original.txt 0 "Datos originales"

# Crear snapshot
python3 mini_gfs/run_client.py snapshot /original.txt /snapshot.txt

# Modificar archivo original
python3 mini_gfs/run_client.py write /original.txt 0 "Datos modificados"

# Verificar que el snapshot mantiene los datos originales
python3 mini_gfs/run_client.py read /snapshot.txt 0 100
python3 mini_gfs/run_client.py read /original.txt 0 100
```

**Resultado esperado:**
- Snapshot creado exitosamente
- Snapshot mantiene los datos originales
- Modificaciones al original no afectan el snapshot (copy-on-write)

---

### QA 18: Renombrar y Eliminar Archivos

**Objetivo:** Probar operaciones de namespace.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /temp.txt
python3 mini_gfs/run_client.py write /temp.txt 0 "Datos temporales"

# Renombrar
python3 mini_gfs/run_client.py rename /temp.txt /renamed.txt

# Verificar que el archivo renombrado existe
python3 mini_gfs/run_client.py read /renamed.txt 0 100

# Listar directorio
python3 mini_gfs/run_client.py listdir /

# Eliminar archivo
python3 mini_gfs/run_client.py delete /renamed.txt

# Verificar que fue eliminado
python3 mini_gfs/run_client.py listdir /
```

**Resultado esperado:**
- Archivo renombrado correctamente
- Listado muestra archivos correctamente
- Archivo eliminado exitosamente

---

### QA 19: Verificar Checksums de Integridad

**Objetivo:** Verificar que el sistema detecta corrupción de datos.

```bash
# Crear y escribir archivo
python3 mini_gfs/run_client.py create /checksum_test.txt
python3 mini_gfs/run_client.py write /checksum_test.txt 0 "Datos para verificar checksums"

# Leer (debería verificar checksums automáticamente)
python3 mini_gfs/run_client.py read /checksum_test.txt 0 100

# Nota: Para probar detección de corrupción, necesitarías
# modificar manualmente un archivo .chunk en data/chunks/
# y luego intentar leerlo - debería fallar o reportar error
```

**Resultado esperado:**
- Lecturas verifican checksums automáticamente
- Sistema detecta corrupción si los datos están dañados

---

### QA 20: Verificar Versionado de Chunks

**Objetivo:** Verificar que los chunks tienen versiones que se incrementan.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /version_test.txt

# Escribir (esto incrementa la versión del chunk)
python3 mini_gfs/run_client.py write /version_test.txt 0 "Primera escritura"

# Ver información del archivo (debería mostrar versión)
python3 mini_gfs/run_client.py ls /version_test.txt

# Escribir de nuevo (incrementa versión nuevamente)
python3 mini_gfs/run_client.py write /version_test.txt 0 "Segunda escritura"
```

**Resultado esperado:**
- Cada mutación incrementa la versión del chunk
- El Master mantiene la versión actual de cada chunk

---

### QA 21: Garbage Collection Automático

**Objetivo:** Verificar que los chunks huérfanos se eliminan automáticamente.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /gc_test.txt
python3 mini_gfs/run_client.py write /gc_test.txt 0 "Datos para GC"

# Obtener información (nota los chunks)
python3 mini_gfs/run_client.py ls /gc_test.txt

# Eliminar archivo
python3 mini_gfs/run_client.py delete /gc_test.txt

# Esperar 3+ días (o modificar garbage_retention_days en el código)
# Los chunks deberían ser eliminados automáticamente por el background worker
```

**Resultado esperado:**
- Chunks marcados como garbage después de eliminar archivo
- Chunks eliminados automáticamente después del período de retención

---

### QA 22: Data Pipeline para Escrituras

**Objetivo:** Verificar que las escrituras usan pipeline eficiente.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /pipeline_test.txt

# Escribir datos grandes (para observar el pipeline)
python3 -c "
data = 'X' * (1024 * 1024)  # 1 MB
with open('/tmp/large_data.txt', 'w') as f:
    f.write(data)
"

# Escribir usando pipeline (automático)
python3 mini_gfs/run_client.py write /pipeline_test.txt 0 "$(cat /tmp/large_data.txt)"

# Verificar que se escribió correctamente
python3 mini_gfs/run_client.py read /pipeline_test.txt 0 100
```

**Resultado esperado:**
- Escrituras usan pipeline (Cliente → Réplica1 → Réplica2 → Réplica3)
- Datos se escriben correctamente en todas las réplicas

---

## Escenarios de Prueba

### QA 4: Escritura en Offset Específico

**Objetivo:** Verificar escritura en posiciones específicas del archivo.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /offset_test.txt

# Escribir datos iniciales
python3 mini_gfs/run_client.py write /offset_test.txt 0 "Inicio del archivo. "
python3 mini_gfs/run_client.py write /offset_test.txt 20 "Medio del archivo. "
python3 mini_gfs/run_client.py write /offset_test.txt 40 "Final del archivo."

# Leer todo
python3 mini_gfs/run_client.py read /offset_test.txt 0 100
```

**Resultado esperado:**
- Datos escritos en las posiciones correctas
- Lectura muestra el contenido completo con los datos en sus offsets

---

### QA 5: Múltiples Archivos Simultáneos

**Objetivo:** Verificar que el sistema maneja múltiples archivos correctamente.

```bash
# Crear múltiples archivos
for i in {1..5}; do
    python3 mini_gfs/run_client.py create "/file$i.txt"
    python3 mini_gfs/run_client.py write "/file$i.txt" 0 "Contenido del archivo $i"
done

# Verificar cada archivo
for i in {1..5}; do
    echo "=== Archivo $i ==="
    python3 mini_gfs/run_client.py ls "/file$i.txt"
    python3 mini_gfs/run_client.py read "/file$i.txt" 0 50
done
```

**Resultado esperado:**
- Todos los archivos creados correctamente
- Cada archivo mantiene su contenido independiente
- Metadatos correctos para cada archivo

---

## Pruebas de Recuperación

### QA 6: Recuperación desde WAL

**Objetivo:** Verificar que el sistema se recupera correctamente desde el Write-Ahead Log.

```bash
# 1. Crear algunos archivos y operaciones
python3 mini_gfs/run_client.py create /recovery_test.txt
python3 mini_gfs/run_client.py write /recovery_test.txt 0 "Datos antes del fallo"
python3 mini_gfs/run_client.py append /recovery_test.txt "Datos después del fallo\n"

# 2. Detener el Master abruptamente (Ctrl+C)
# 3. Verificar que el WAL existe
ls -lh data/master/wal.log

# 4. Reiniciar el Master
python3 mini_gfs/run_master.py

# 5. Verificar que los datos se recuperaron
python3 mini_gfs/run_client.py read /recovery_test.txt 0 200
python3 mini_gfs/run_client.py ls /recovery_test.txt
```

**Resultado esperado:**
- WAL contiene las operaciones registradas
- Al reiniciar, el Master carga el snapshot y aplica el WAL
- Todos los datos se recuperan correctamente
- Archivo existe con su contenido completo

---

### QA 7: Recuperación sin Snapshot (Solo WAL)

**Objetivo:** Verificar recuperación completa desde el WAL cuando no hay snapshot.

```bash
# 1. Eliminar el snapshot (si existe)
rm -f data/master/metadata_snapshot.json

# 2. Detener el Master
# 3. Crear operaciones (esto solo actualizará el WAL)
# Nota: Necesitarás reiniciar el Master primero
python3 mini_gfs/run_master.py

# 4. Crear archivos
python3 mini_gfs/run_client.py create /wal_only_test.txt
python3 mini_gfs/run_client.py write /wal_only_test.txt 0 "Solo en WAL"

# 5. Detener el Master
# 6. Reiniciar (debería cargar solo desde WAL)
python3 mini_gfs/run_master.py

# 7. Verificar recuperación
python3 mini_gfs/run_client.py read /wal_only_test.txt 0 50
```

**Resultado esperado:**
- Master se inicia correctamente sin snapshot
- WAL se reproduce completamente
- Todos los archivos y datos se recuperan

---

## Pruebas de Concurrencia

### QA 8: Múltiples Escrituras Concurrentes

**Objetivo:** Verificar que el sistema maneja operaciones concurrentes.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /concurrent.txt

# Ejecutar múltiples escrituras en paralelo
for i in {1..10}; do
    (
        python3 mini_gfs/run_client.py write /concurrent.txt $((i*10)) "Thread $i: "
    ) &
done

# Esperar a que terminen
wait

# Leer resultado
python3 mini_gfs/run_client.py read /concurrent.txt 0 200
```

**Resultado esperado:**
- Todas las escrituras se completan
- No hay corrupción de datos
- El contenido final refleja todas las escrituras

---

### QA 9: Múltiples Record Appends Concurrentes

**Objetivo:** Probar record append con múltiples clientes simultáneos.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /concurrent_append.txt

# Ejecutar múltiples appends en paralelo
for i in {1..20}; do
    (
        python3 mini_gfs/run_client.py append /concurrent_append.txt "Record $i\n"
    ) &
done

# Esperar
wait

# Leer resultado
python3 mini_gfs/run_client.py read /concurrent_append.txt 0 500
```

**Resultado esperado:**
- Todos los records se añaden (puede haber algunos duplicados o pérdidas en caso de race conditions, dependiendo de la implementación)
- El archivo contiene múltiples records

---

## Pruebas de Replicación

### QA 10: Fallo de ChunkServer y Re-replicación

**Objetivo:** Verificar detección de fallos y re-replicación automática.

```bash
# 1. Crear archivo con datos
python3 mini_gfs/run_client.py create /replication_test.txt
python3 mini_gfs/run_client.py write /replication_test.txt 0 "Datos importantes que deben replicarse"

# 2. Verificar información del archivo (nota los chunkservers)
python3 mini_gfs/run_client.py ls /replication_test.txt

# 3. Detener uno de los ChunkServers (Ctrl+C en su terminal)
# Por ejemplo, detener cs1

# 4. Esperar 30-40 segundos para que el Master detecte el fallo
# Deberías ver en el Master:
# "ChunkServers muertos detectados: ['cs1']"
# "Chunks que necesitan re-replicación: 1"

# 5. Verificar que el archivo sigue siendo accesible
python3 mini_gfs/run_client.py read /replication_test.txt 0 100

# 6. Verificar que se creó una nueva réplica
python3 mini_gfs/run_client.py ls /replication_test.txt
# Deberías ver que el chunk ahora tiene réplicas en cs2, cs3, y posiblemente otro
```

**Resultado esperado:**
- Master detecta el ChunkServer muerto
- Identifica chunks que necesitan re-replicación
- Re-replica automáticamente a otro ChunkServer
- Datos siguen siendo accesibles
- Nuevas réplicas aparecen en la información del archivo

---

### QA 11: Fallo Múltiple de ChunkServers

**Objetivo:** Verificar comportamiento cuando múltiples ChunkServers fallan.

```bash
# 1. Crear archivo
python3 mini_gfs/run_client.py create /multi_failure.txt
python3 mini_gfs/run_client.py write /multi_failure.txt 0 "Test de fallos múltiples"

# 2. Detener 2 de los 3 ChunkServers (dejar solo uno activo)
# Detener cs1 y cs2, dejar cs3

# 3. Esperar detección de fallos

# 4. Intentar leer (debería funcionar si hay al menos una réplica)
python3 mini_gfs/run_client.py read /multi_failure.txt 0 100

# 5. Intentar escribir (puede fallar si no hay suficientes réplicas)
python3 mini_gfs/run_client.py write /multi_failure.txt 0 "Nuevos datos"
```

**Resultado esperado:**
- Master detecta múltiples fallos
- Lectura funciona si hay al menos una réplica viva
- Escritura puede fallar si no hay suficientes réplicas para el replication_factor

---

## Verificación del WAL

### QA 12: Inspeccionar el Write-Ahead Log

**Objetivo:** Ver el contenido del WAL para entender cómo se registran las operaciones.

```bash
# 1. Realizar algunas operaciones
python3 mini_gfs/run_client.py create /wal_inspect.txt
python3 mini_gfs/run_client.py write /wal_inspect.txt 0 "Datos de prueba"
python3 mini_gfs/run_client.py append /wal_inspect.txt "Más datos\n"

# 2. Ver el contenido del WAL
cat data/master/wal.log | python3 -m json.tool

# O ver las últimas líneas
tail -n 5 data/master/wal.log | python3 -m json.tool
```

**Resultado esperado:**
- WAL contiene entradas JSON con:
  - `sequence`: Número de secuencia
  - `timestamp`: Timestamp de la operación
  - `operation`: Tipo de operación (CREATE_FILE, ALLOCATE_CHUNK, etc.)
  - `data`: Datos de la operación

---

### QA 13: Verificar Snapshots

**Objetivo:** Inspeccionar los snapshots de metadatos.

```bash
# 1. Realizar operaciones
python3 mini_gfs/run_client.py create /snapshot_test.txt
python3 mini_gfs/run_client.py write /snapshot_test.txt 0 "Datos para snapshot"

# 2. Esperar 60 segundos para que se genere un snapshot automático
# O forzar guardado deteniendo el Master (Ctrl+C) y reiniciándolo

# 3. Ver el snapshot
cat data/master/metadata_snapshot.json | python3 -m json.tool
```

**Resultado esperado:**
- Snapshot contiene:
  - `files`: Información de todos los archivos
  - `chunks`: Información de todos los chunks
  - `chunkservers`: Información de todos los ChunkServers
  - `snapshot_time`: Timestamp del snapshot

---

## Escenarios Avanzados

### QA 14: Archivo Grande con Múltiples Chunks

**Objetivo:** Probar el sistema con un archivo que ocupe muchos chunks.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /huge_file.txt

# Escribir datos en múltiples chunks
# (Adapta esto según tu implementación del cliente)
for i in {0..4}; do
    offset=$((i * 1024 * 1024))  # Cada chunk es 1 MB
    data=$(python3 -c "print('X' * 1024 * 1024)")
    python3 mini_gfs/run_client.py write /huge_file.txt $offset "$data"
done

# Ver información
python3 mini_gfs/run_client.py ls /huge_file.txt

# Leer desde diferentes chunks
python3 mini_gfs/run_client.py read /huge_file.txt 0 100
python3 mini_gfs/run_client.py read /huge_file.txt $((1024*1024)) 100
```

**Resultado esperado:**
- Archivo creado con múltiples chunks
- Cada chunk tiene sus réplicas
- Lectura funciona desde cualquier offset

---

### QA 15: Stress Test - Múltiples Operaciones

**Objetivo:** Probar el sistema bajo carga.

```bash
# Crear muchos archivos
for i in {1..50}; do
    python3 mini_gfs/run_client.py create "/stress_test_$i.txt" &
done
wait

# Escribir en todos
for i in {1..50}; do
    python3 mini_gfs/run_client.py write "/stress_test_$i.txt" 0 "Contenido $i" &
done
wait

# Leer todos
for i in {1..50}; do
    python3 mini_gfs/run_client.py read "/stress_test_$i.txt" 0 50 &
done
wait

# Verificar algunos
python3 mini_gfs/run_client.py ls /stress_test_1.txt
python3 mini_gfs/run_client.py ls /stress_test_25.txt
python3 mini_gfs/run_client.py ls /stress_test_50.txt
```

**Resultado esperado:**
- Todas las operaciones se completan
- No hay errores o corrupción
- Sistema mantiene consistencia

---

## Verificación de Consistencia

### QA 16: Verificar Réplicas en Múltiples ChunkServers

**Objetivo:** Confirmar que los datos están replicados correctamente.

```bash
# 1. Crear archivo y escribir datos
python3 mini_gfs/run_client.py create /replica_check.txt
python3 mini_gfs/run_client.py write /replica_check.txt 0 "Datos replicados"

# 2. Obtener información del archivo
python3 mini_gfs/run_client.py ls /replica_check.txt

# 3. Verificar que el chunk existe en múltiples ChunkServers
# (Nota: necesitarás inspeccionar los directorios de datos)
ls -lh data/chunks/cs1/*.chunk
ls -lh data/chunks/cs2/*.chunk
ls -lh data/chunks/cs3/*.chunk

# 4. Comparar contenido de réplicas (deberían ser idénticas)
# (Requiere acceso directo a los archivos de chunks)
```

**Resultado esperado:**
- Chunk aparece en múltiples directorios de ChunkServers
- Tamaños de archivos son idénticos
- Contenido es el mismo (si puedes leerlo directamente)

---

## Troubleshooting

### Problemas Comunes

**Problema:** Master no detecta ChunkServers
- **Solución:** Verifica que los ChunkServers estén corriendo y que las direcciones sean correctas

**Problema:** Error al escribir/leer
- **Solución:** Verifica que el archivo existe y que hay ChunkServers disponibles

**Problema:** Re-replicación no funciona
- **Solución:** Asegúrate de tener al menos 3 ChunkServers para replication_factor=3

**Problema:** WAL no se recupera
- **Solución:** Verifica permisos de escritura en `data/master/` y que el archivo WAL existe

---

## Notas Finales

- Los tiempos de heartbeat y detección de fallos son configurables en `configs/master.yaml`
- El WAL se escribe inmediatamente (fsync) para garantizar durabilidad
- Los snapshots se generan periódicamente (cada 60 segundos por defecto)
- La re-replicación es automática pero puede tardar unos segundos en detectarse

---

---

## Pruebas de Características Avanzadas

### QA 23: Snapshot con Múltiples Referencias

**Objetivo:** Verificar que los snapshots comparten chunks correctamente.

```bash
# Crear archivo original
python3 mini_gfs/run_client.py create /shared.txt
python3 mini_gfs/run_client.py write /shared.txt 0 "Datos compartidos"

# Crear múltiples snapshots
python3 mini_gfs/run_client.py snapshot /shared.txt /snap1.txt
python3 mini_gfs/run_client.py snapshot /shared.txt /snap2.txt
python3 mini_gfs/run_client.py snapshot /shared.txt /snap3.txt

# Verificar que todos comparten los mismos chunks
python3 mini_gfs/run_client.py ls /shared.txt
python3 mini_gfs/run_client.py ls /snap1.txt
# Los chunk_handles deberían ser los mismos
```

**Resultado esperado:**
- Múltiples snapshots comparten los mismos chunks
- reference_count se incrementa correctamente

---

### QA 24: Verificar Awareness de Racks

**Objetivo:** Verificar que las réplicas se distribuyen entre racks.

```bash
# Configurar ChunkServers en diferentes racks (editar configs/chunkserver.yaml)
# rack_id: rack-a, rack-b, rack-c

# Crear archivo
python3 mini_gfs/run_client.py create /rack_test.txt
python3 mini_gfs/run_client.py write /rack_test.txt 0 "Test de racks"

# Ver información - las réplicas deberían estar en racks diferentes
python3 mini_gfs/run_client.py ls /rack_test.txt
```

**Resultado esperado:**
- Réplicas distribuidas entre racks diferentes cuando es posible
- Mejor tolerancia a fallos de infraestructura

---

### QA 25: Verificar Versionado en Re-replicación

**Objetivo:** Verificar que las réplicas obsoletas se detectan por versión.

```bash
# Crear archivo
python3 mini_gfs/run_client.py create /version_replica.txt
python3 mini_gfs/run_client.py write /version_replica.txt 0 "Datos iniciales"

# Detener un ChunkServer
# Escribir más datos (incrementa versión)
python3 mini_gfs/run_client.py write /version_replica.txt 0 "Datos actualizados"

# Reiniciar ChunkServer detenido
# El Master debería detectar que tiene versión obsoleta
# y re-replicar desde una réplica con versión actual
```

**Resultado esperado:**
- ChunkServer con versión obsoleta se detecta
- Re-replicación usa réplicas con versión actual

---

¡Disfruta explorando el Mini Google File System con todas sus características avanzadas!

