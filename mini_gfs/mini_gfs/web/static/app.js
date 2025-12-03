// API base URL
const API_BASE = '/api';

// Variables globales
let topologyData = null;
let distributionData = null;
let currentFileView = null;

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    updateSystemStatus();
    loadNetworkTopology();
    loadChunkDistribution();
    loadFiles();
    loadMetrics();
    loadConfig();
    
    // Auto-actualización
    setInterval(updateSystemStatus, 5000);
    setInterval(loadNetworkTopology, 3000);
    setInterval(loadChunkDistribution, 5000);
    setInterval(loadMetrics, 5000);
});

// ========== Control del Sistema ==========

async function startSystem() {
    try {
        const response = await fetch(`${API_BASE}/system/start`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            alert('Sistema iniciado correctamente');
            updateSystemStatus();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error iniciando sistema: ' + error.message);
    }
}

async function stopSystem() {
    if (!confirm('¿Está seguro de que desea detener el sistema?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/system/stop`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            alert('Sistema detenido');
            updateSystemStatus();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error deteniendo sistema: ' + error.message);
    }
}

// ========== Gestión de ChunkServers ==========

async function addChunkserver() {
    if (!confirm('¿Desea agregar un nuevo ChunkServer? El puerto se asignará automáticamente.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/chunkservers/add`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}\nChunkServer ID: ${data.chunkserver_id}\nPuerto: ${data.port}`);
            updateSystemStatus();
            loadNetworkTopology();
            loadChunkDistribution();
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        alert('Error agregando ChunkServer: ' + error.message);
    }
}

async function removeChunkserver(chunkserverId) {
    if (!confirm(`¿Está seguro de que desea quitar el ChunkServer ${chunkserverId}?\n\nNota: Podrá restaurarlo más tarde desde la lista.`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/chunkservers/remove`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunkserver_id: chunkserverId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            updateSystemStatus();
            loadNetworkTopology();
            loadChunkDistribution();
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        alert('Error quitando ChunkServer: ' + error.message);
    }
}

async function restoreChunkserver(chunkserverId) {
    if (!confirm(`¿Desea restaurar el ChunkServer ${chunkserverId}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/chunkservers/restore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunkserver_id: chunkserverId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}\nChunkServer ID: ${data.chunkserver_id}\nPuerto: ${data.port}`);
            updateSystemStatus();
            loadNetworkTopology();
            loadChunkDistribution();
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        alert('Error restaurando ChunkServer: ' + error.message);
    }
}

async function updateSystemStatus() {
    try {
        const response = await fetch(`${API_BASE}/system/status`);
        const data = await response.json();
        
        if (data.success) {
            // Master
            const masterStatus = data.master.status === 'running' ? 'running' : 'stopped';
            document.getElementById('master-status').className = `status-indicator ${masterStatus}`;
            document.getElementById('master-pid').textContent = data.master.pid ? `(PID: ${data.master.pid})` : '';
            
            // ChunkServers dinámicos
            const chunkserversList = document.getElementById('chunkservers-list');
            chunkserversList.innerHTML = '';
            
            const chunkservers = data.chunkservers || {};
            const chunkserverIds = Object.keys(chunkservers).sort();
            
            if (chunkserverIds.length === 0) {
                chunkserversList.innerHTML = '<p style="color: #999;">No hay ChunkServers (activos o detenidos)</p>';
            } else {
                chunkserverIds.forEach(csId => {
                    const csData = chunkservers[csId];
                    const status = csData.running ? 'running' : 'stopped';
                    const statusText = csData.running ? 'Vivo' : 'Detenido';
                    const canRestore = csData.can_restore === true;
                    
                    const statusItem = document.createElement('div');
                    statusItem.className = 'status-item';
                    statusItem.id = `status-${csId}`;
                    statusItem.style.marginBottom = '8px';
                    statusItem.style.padding = '8px';
                    statusItem.style.border = '1px solid #ddd';
                    statusItem.style.borderRadius = '4px';
                    statusItem.style.backgroundColor = csData.running ? '#f9f9f9' : '#fff3cd';
                    
                    let buttonsHtml = '';
                    if (csData.running) {
                        buttonsHtml = `
                            <button onclick="removeChunkserver('${csId}')" 
                                    style="margin-left: 10px; background: #e74c3c; color: white; padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px;">
                                🗑️ Quitar
                            </button>
                        `;
                    } else if (canRestore) {
                        buttonsHtml = `
                            <button onclick="restoreChunkserver('${csId}')" 
                                    style="margin-left: 10px; background: #2ecc71; color: white; padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px;">
                                ▶️ Restaurar
                            </button>
                        `;
                    }
                    
                    statusItem.innerHTML = `
                        <span class="status-label">${csId}:</span>
                        <span class="status-indicator ${status}">●</span>
                        <span>${statusText}</span>
                        <span>${csData.pid ? `(PID: ${csData.pid})` : ''}</span>
                        <span>${csData.port ? `(Puerto: ${csData.port})` : ''}</span>
                        ${buttonsHtml}
                    `;
                    chunkserversList.appendChild(statusItem);
                });
            }
        }
    } catch (error) {
        console.error('Error actualizando estado:', error);
    }
}

// ========== Topología de Red ==========

async function loadNetworkTopology() {
    try {
        const response = await fetch(`${API_BASE}/system/topology`);
        const data = await response.json();
        
        if (data.success) {
            topologyData = data;
            renderNetworkTopology(data);
        }
    } catch (error) {
        console.error('Error cargando topología:', error);
    }
}

function renderNetworkTopology(data) {
    const svg = d3.select('#topology-svg');
    svg.selectAll('*').remove();
    
    const width = svg.node().getBoundingClientRect().width || 800;
    const height = 500;
    svg.attr('width', width).attr('height', height);
    
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.3;
    
    const master = data.master;
    const chunkservers = data.chunkservers || [];
    
    // Dibujar Master en el centro
    const masterGroup = svg.append('g').attr('class', 'master-node');
    masterGroup.append('circle')
        .attr('cx', centerX)
        .attr('cy', centerY)
        .attr('r', 40)
        .attr('fill', '#3498db')
        .attr('stroke', '#000')
        .attr('stroke-width', 3);
    
    masterGroup.append('text')
        .attr('x', centerX)
        .attr('y', centerY)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', 'white')
        .attr('font-size', '24px')
        .attr('font-weight', 'bold')
        .text('M');
    
    masterGroup.append('text')
        .attr('x', centerX)
        .attr('y', centerY + 60)
        .attr('text-anchor', 'middle')
        .attr('font-size', '14px')
        .attr('font-weight', 'bold')
        .text('Master');
    
    // Tooltip para Master
    masterGroup.append('title')
        .text(`Master\n${master.address}\n${master.description}`);
    
    // Dibujar ChunkServers en círculo
    chunkservers.forEach((cs, i) => {
        const angle = (i * 2 * Math.PI / chunkservers.length) - Math.PI / 2;
        const csX = centerX + radius * Math.cos(angle);
        const csY = centerY + radius * Math.sin(angle);
        
        const color = cs.status === 'alive' ? '#2ecc71' : '#e74c3c';
        
        const csGroup = svg.append('g').attr('class', `chunkserver-node cs-${cs.id}`);
        
        // Línea de conexión
        svg.append('line')
            .attr('x1', centerX)
            .attr('y1', centerY)
            .attr('x2', csX)
            .attr('y2', csY)
            .attr('stroke', '#95a5a6')
            .attr('stroke-width', 2)
            .attr('opacity', 0.6);
        
        // Círculo del ChunkServer
        csGroup.append('circle')
            .attr('cx', csX)
            .attr('cy', csY)
            .attr('r', 30)
            .attr('fill', color)
            .attr('stroke', '#000')
            .attr('stroke-width', 2)
            .classed('pulsing', cs.status === 'alive');
        
        csGroup.append('text')
            .attr('x', csX)
            .attr('y', csY)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('fill', 'white')
            .attr('font-size', '18px')
            .attr('font-weight', 'bold')
            .text(cs.id.slice(-1));
        
        // Etiqueta del ChunkServer
        const labelY = csY > centerY ? csY + 50 : csY - 50;
        csGroup.append('text')
            .attr('x', csX)
            .attr('y', labelY)
            .attr('text-anchor', 'middle')
            .attr('font-size', '12px')
            .attr('font-weight', 'bold')
            .text(`${cs.id}\n${cs.chunks_count} chunks\n${cs.status === 'alive' ? 'Vivo' : 'Muerto'}`);
        
        // Tooltip
        csGroup.append('title')
            .text(`${cs.id}\n${cs.address}\nChunks: ${cs.chunks_count}\nEstado: ${cs.status}`);
        
        // Hover effect
        csGroup.selectAll('circle, text')
            .on('mouseover', function() {
                d3.select(this).attr('opacity', 0.7);
            })
            .on('mouseout', function() {
                d3.select(this).attr('opacity', 1);
            });
    });
}

// ========== Distribución de Chunks ==========

async function loadChunkDistribution(filePath = null) {
    try {
        let url = `${API_BASE}/chunks/distribution`;
        if (filePath) {
            url += `?file_path=${encodeURIComponent(filePath)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            distributionData = data;
            const viewType = document.querySelector('input[name="view-type"]:checked').value;
            renderChunkDistribution(data, viewType);
        }
    } catch (error) {
        console.error('Error cargando distribución:', error);
    }
}

function updateChunkDistributionView() {
    const viewType = document.querySelector('input[name="view-type"]:checked').value;
    const fileSelector = document.getElementById('file-selector');
    
    if (viewType === 'file') {
        fileSelector.style.display = 'block';
        loadFilesForSelector();
    } else {
        fileSelector.style.display = 'none';
    }
    
    if (distributionData) {
        renderChunkDistribution(distributionData, viewType);
    }
}

async function loadFilesForSelector() {
    try {
        const response = await fetch(`${API_BASE}/files/list`);
        const data = await response.json();
        
        if (data.success) {
            const selector = document.getElementById('file-selector');
            selector.innerHTML = '<option value="">Seleccionar archivo...</option>';
            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file;
                option.textContent = file;
                selector.appendChild(option);
            });
            
            selector.onchange = function() {
                if (this.value) {
                    loadChunkDistribution(this.value);
                }
            };
        }
    } catch (error) {
        console.error('Error cargando archivos para selector:', error);
    }
}

function renderChunkDistribution(data, viewType) {
    if (viewType === 'general') {
        renderGeneralDistribution(data);
    } else {
        renderFileDistribution(data);
    }
}

function renderGeneralDistribution(data) {
    document.getElementById('distribution-general').style.display = 'block';
    document.getElementById('distribution-file').style.display = 'none';
    
    const chunks = data.chunks || [];
    const summary = data.summary || {};
    const chunkserversStats = summary.chunkservers_stats || {};
    
    // Gráfico de barras
    const chartContainer = document.getElementById('distribution-chart');
    chartContainer.innerHTML = '';
    
    const svg = d3.select('#distribution-chart')
        .append('svg')
        .attr('width', chartContainer.offsetWidth || 800)
        .attr('height', 300);
    
    const csIds = Object.keys(chunkserversStats);
    const counts = csIds.map(csId => chunkserversStats[csId].total_chunks);
    const maxCount = Math.max(...counts, 1);
    
    const margin = { top: 20, right: 20, bottom: 40, left: 40 };
    const width = (chartContainer.offsetWidth || 800) - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;
    
    const x = d3.scaleBand()
        .domain(csIds)
        .range([0, width])
        .padding(0.2);
    
    const y = d3.scaleLinear()
        .domain([0, maxCount])
        .range([height, 0]);
    
    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);
    
    g.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(x));
    
    g.append('g')
        .call(d3.axisLeft(y));
    
    g.selectAll('.bar')
        .data(csIds)
        .enter().append('rect')
        .attr('class', 'bar')
        .attr('x', d => x(d))
        .attr('width', x.bandwidth())
        .attr('y', d => y(chunkserversStats[d].total_chunks))
        .attr('height', d => height - y(chunkserversStats[d].total_chunks))
        .attr('fill', '#667eea')
        .append('title')
        .text(d => `${d}: ${chunkserversStats[d].total_chunks} chunks`);
    
    // Tabla
    const tableContainer = document.getElementById('distribution-table-container');
    tableContainer.innerHTML = '<h4>Tabla de Chunks</h4>';
    
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Chunk Handle</th>
            <th>Archivo</th>
            <th>ChunkServers</th>
            <th>Tamaño</th>
            <th>Versión</th>
            <th>Estado</th>
        </tr>
    `;
    table.appendChild(thead);
    
    const tbody = document.createElement('tbody');
    chunks.forEach(chunk => {
        const row = document.createElement('tr');
        const statusClass = chunk.replication_status === 'complete' ? '' : 'style="background: #ffebee;"';
        row.innerHTML = `
            <td>${chunk.handle.substring(0, 12)}...</td>
            <td>${chunk.file_path || 'N/A'}</td>
            <td>${chunk.chunkservers.join(', ')}</td>
            <td>${(chunk.size / 1024).toFixed(2)} KB</td>
            <td>${chunk.version}</td>
            <td ${statusClass}>${chunk.replication_status === 'complete' ? '✓ Completo' : '⚠ Sub-replicado'}</td>
        `;
        tbody.appendChild(row);
    });
    table.appendChild(tbody);
    tableContainer.appendChild(table);
}

function renderFileDistribution(data) {
    document.getElementById('distribution-general').style.display = 'none';
    document.getElementById('distribution-file').style.display = 'block';
    
    const chunks = data.chunks || [];
    const filePath = data.file_path;
    
    const diagramContainer = document.getElementById('file-chunks-diagram');
    diagramContainer.innerHTML = `<h4>Archivo: ${filePath || 'N/A'}</h4>`;
    
    if (chunks.length === 0) {
        diagramContainer.innerHTML += '<p>No hay chunks para este archivo.</p>';
        return;
    }
    
    // Crear diagrama visual
    const svg = d3.select('#file-chunks-diagram')
        .append('svg')
        .attr('width', diagramContainer.offsetWidth || 800)
        .attr('height', Math.max(400, chunks.length * 100));
    
    chunks.forEach((chunk, i) => {
        const y = i * 100 + 50;
        const x = 100;
        
        // Caja del chunk
        svg.append('rect')
            .attr('x', x)
            .attr('y', y - 20)
            .attr('width', 150)
            .attr('height', 40)
            .attr('fill', chunk.replication_status === 'complete' ? '#2ecc71' : '#f39c12')
            .attr('stroke', '#000')
            .attr('stroke-width', 2);
        
        svg.append('text')
            .attr('x', x + 75)
            .attr('y', y)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-weight', 'bold')
            .text(`Chunk ${i + 1}`);
        
        // Réplicas
        chunk.chunkservers.forEach((csId, j) => {
            const replicaX = 300 + j * 100;
            svg.append('circle')
                .attr('cx', replicaX)
                .attr('cy', y)
                .attr('r', 15)
                .attr('fill', '#3498db')
                .attr('stroke', '#000')
                .attr('stroke-width', 2);
            
            svg.append('text')
                .attr('x', replicaX)
                .attr('y', y + 30)
                .attr('text-anchor', 'middle')
                .attr('font-size', '10px')
                .text(csId);
            
            // Línea de conexión
            svg.append('line')
                .attr('x1', x + 150)
                .attr('y1', y)
                .attr('x2', replicaX)
                .attr('y2', y)
                .attr('stroke', '#95a5a6')
                .attr('stroke-width', 1);
        });
    });
    
    // Tabla de chunks del archivo
    const tableContainer = document.getElementById('file-chunks-table');
    tableContainer.innerHTML = '<h4>Chunks del Archivo</h4>';
    
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Índice</th>
            <th>Chunk Handle</th>
            <th>Réplicas</th>
            <th>Tamaño</th>
            <th>Estado</th>
        </tr>
    `;
    table.appendChild(thead);
    
    const tbody = document.createElement('tbody');
    chunks.forEach((chunk, i) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${i + 1}</td>
            <td>${chunk.handle.substring(0, 12)}...</td>
            <td>${chunk.chunkservers.join(', ')} (${chunk.replicas_count}/${chunk.replication_factor})</td>
            <td>${(chunk.size / 1024).toFixed(2)} KB</td>
            <td>${chunk.replication_status === 'complete' ? '✓ Completo' : '⚠ Sub-replicado'}</td>
        `;
        tbody.appendChild(row);
    });
    table.appendChild(tbody);
    tableContainer.appendChild(table);
}

// ========== Archivos ==========

async function loadFiles() {
    try {
        const response = await fetch(`${API_BASE}/files/list`);
        const data = await response.json();
        
        if (data.success) {
            const filesList = document.getElementById('files-list');
            filesList.innerHTML = '<h3>Archivos en el Sistema</h3>';
            
            if (data.files.length === 0) {
                filesList.innerHTML += '<p>No hay archivos en el sistema.</p>';
                return;
            }
            
            data.files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <span>${file}</span>
                    <div>
                        <button onclick="viewFileInfo('${file}')">ℹ️ Ver Info</button>
                        <button onclick="readFileComplete('${file}')">📖 Leer Archivo</button>
                        <button onclick="deleteFile('${file}')">🗑️ Eliminar</button>
                    </div>
                `;
                filesList.appendChild(fileItem);
            });
        }
    } catch (error) {
        console.error('Error cargando archivos:', error);
    }
}

// Funciones de diálogos
function showFileOperationDialog(operation) {
    // Ocultar todos los diálogos
    document.querySelectorAll('.operation-dialog').forEach(d => d.style.display = 'none');
    
    // Mostrar el diálogo solicitado
    const dialog = document.getElementById(`dialog-${operation}`);
    if (dialog) {
        dialog.style.display = 'block';
        // Limpiar campos, pero preservar info-path si ya tiene un valor (para viewFileInfo)
        dialog.querySelectorAll('input, textarea').forEach(input => {
            if (input.id === 'info-path' && input.value) {
                // No limpiar info-path si ya tiene un valor
                return;
            }
            if (input.type !== 'number' || input.id === 'write-offset' || input.id === 'read-offset') {
                input.value = '';
            }
        });
    }
}

function hideFileOperationDialog(operation) {
    const dialog = document.getElementById(`dialog-${operation}`);
    if (dialog) {
        dialog.style.display = 'none';
    }
}

// Crear archivo
async function createFile() {
    const path = document.getElementById('create-path').value;
    
    if (!path) {
        alert('Por favor ingrese una ruta de archivo');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        
        const data = await response.json();
        if (data.success) {
            alert('Archivo creado correctamente');
            hideFileOperationDialog('create');
            loadFiles();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error creando archivo: ' + error.message);
    }
}

// Escribir en archivo
async function writeFile() {
    const path = document.getElementById('write-path').value;
    const offset = parseInt(document.getElementById('write-offset').value) || 0;
    const content = document.getElementById('write-content').value;
    
    if (!path) {
        alert('Por favor ingrese una ruta de archivo');
        return;
    }
    
    if (!content) {
        alert('Por favor ingrese contenido a escribir');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/write`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, offset, content })
        });
        
        const data = await response.json();
        if (data.success) {
            alert(data.message || 'Datos escritos correctamente');
            hideFileOperationDialog('write');
            loadFiles();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error escribiendo archivo: ' + error.message);
    }
}

// Leer archivo
async function readFile() {
    const path = document.getElementById('read-path').value;
    const offset = parseInt(document.getElementById('read-offset').value) || 0;
    const length = parseInt(document.getElementById('read-length').value) || 100;
    
    if (!path) {
        alert('Por favor ingrese una ruta de archivo');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/read`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, offset, length })
        });
        
        const data = await response.json();
        if (data.success) {
            const resultDiv = document.getElementById('read-result');
            const contentDiv = document.getElementById('read-content');
            
            if (data.is_text) {
                contentDiv.textContent = data.content;
            } else {
                contentDiv.textContent = `Datos (hex): ${data.content}\n\nBytes leídos: ${data.bytes_read}`;
            }
            
            resultDiv.style.display = 'block';
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error leyendo archivo: ' + error.message);
    }
}

// Append a archivo
async function appendFile() {
    const path = document.getElementById('append-path').value;
    const content = document.getElementById('append-content').value;
    
    if (!path) {
        alert('Por favor ingrese una ruta de archivo');
        return;
    }
    
    if (!content) {
        alert('Por favor ingrese contenido a añadir');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/append`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, content })
        });
        
        const data = await response.json();
        if (data.success) {
            alert(data.message || 'Datos añadidos correctamente');
            hideFileOperationDialog('append');
            loadFiles();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error añadiendo datos: ' + error.message);
    }
}

// Obtener información de archivo (ls)
async function getFileInfo(filePath = null) {
    // Si se proporciona un path como parámetro, usarlo; si no, leer del campo del formulario
    const path = filePath || document.getElementById('info-path').value;
    
    if (!path) {
        alert('Por favor ingrese una ruta de archivo');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/info?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (data.success) {
            const resultDiv = document.getElementById('info-result');
            const contentDiv = document.getElementById('info-content');
            
            let info = `Archivo: ${data.path}\n\n`;
            info += `Chunks: ${data.chunk_handles.length}\n\n`;
            info += 'Información de Chunks:\n';
            data.chunks_info.forEach((chunk, i) => {
                info += `\nChunk ${i + 1}:\n`;
                info += `  Handle: ${chunk.chunk_handle}\n`;
                info += `  Réplicas: ${chunk.replicas.map(r => r.chunkserver_id).join(', ')}\n`;
                info += `  Primary: ${chunk.primary_id || 'N/A'}\n`;
                info += `  Tamaño: ${chunk.size} bytes\n`;
            });
            
            contentDiv.textContent = info;
            resultDiv.style.display = 'block';
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error obteniendo información: ' + error.message);
    }
}

// Crear snapshot
async function snapshotFile() {
    const sourcePath = document.getElementById('snapshot-source').value;
    const destPath = document.getElementById('snapshot-dest').value;
    
    if (!sourcePath || !destPath) {
        alert('Por favor ingrese ambas rutas (fuente y destino)');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/snapshot`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_path: sourcePath, dest_path: destPath })
        });
        
        const data = await response.json();
        if (data.success) {
            alert(data.message || 'Snapshot creado correctamente');
            hideFileOperationDialog('snapshot');
            loadFiles();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error creando snapshot: ' + error.message);
    }
}

// Renombrar archivo
async function renameFile() {
    const oldPath = document.getElementById('rename-old').value;
    const newPath = document.getElementById('rename-new').value;
    
    if (!oldPath || !newPath) {
        alert('Por favor ingrese ambas rutas (antigua y nueva)');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_path: oldPath, new_path: newPath })
        });
        
        const data = await response.json();
        if (data.success) {
            alert(data.message || 'Archivo renombrado correctamente');
            hideFileOperationDialog('rename');
            loadFiles();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error renombrando archivo: ' + error.message);
    }
}

// Eliminar archivo (versión mejorada)
async function deleteFile(filePath) {
    // Si se llama desde el botón del diálogo
    if (!filePath) {
        filePath = document.getElementById('delete-path').value;
        if (!filePath) {
            alert('Por favor ingrese una ruta de archivo');
            return;
        }
    }
    
    if (!confirm(`¿Está seguro de que desea eliminar ${filePath}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/files/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: filePath })
        });
        
        const data = await response.json();
        if (data.success) {
            alert('Archivo eliminado');
            if (document.getElementById('delete-path')) {
                hideFileOperationDialog('delete');
            }
            loadFiles();
            loadChunkDistribution();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error eliminando archivo: ' + error.message);
    }
}

// Función auxiliar para ver info desde la lista
async function viewFileInfo(filePath) {
    // Mostrar el diálogo y establecer el valor del campo
    showFileOperationDialog('info');
    document.getElementById('info-path').value = filePath;
    // Llamar a getFileInfo pasando el path directamente como parámetro
    getFileInfo(filePath);
}

// Función para leer archivo completo desde la lista
async function readFileComplete(filePath) {
    try {
        // Leer el archivo completo (sin especificar length, el servidor leerá todo)
        const response = await fetch(`${API_BASE}/files/read`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: filePath, offset: 0 })
        });
        
        const data = await response.json();
        if (data.success) {
            // Mostrar el resultado en un diálogo
            const resultDiv = document.getElementById('read-result');
            const contentDiv = document.getElementById('read-content');
            
            if (data.is_text) {
                contentDiv.textContent = data.content;
            } else {
                contentDiv.textContent = `Datos (hex): ${data.content}\n\nBytes leídos: ${data.bytes_read}`;
            }
            
            // Mostrar el diálogo de lectura
            document.getElementById('read-path').value = filePath;
            showFileOperationDialog('read');
            resultDiv.style.display = 'block';
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error leyendo archivo: ' + error.message);
    }
}

// ========== Configuración ==========

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/config/get`);
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('config-replication').value = data.replication_factor;
            document.getElementById('config-chunk-size').value = data.chunk_size / 1048576; // Convertir a MB
            document.getElementById('config-heartbeat').value = data.heartbeat_timeout;
            document.getElementById('config-lease').value = data.lease_duration;
        }
    } catch (error) {
        console.error('Error cargando configuración:', error);
    }
}

async function updateConfig() {
    const config = {
        replication_factor: parseInt(document.getElementById('config-replication').value),
        chunk_size: parseInt(document.getElementById('config-chunk-size').value) * 1048576,
        heartbeat_timeout: parseInt(document.getElementById('config-heartbeat').value),
        lease_duration: parseInt(document.getElementById('config-lease').value)
    };
    
    try {
        const response = await fetch(`${API_BASE}/config/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const data = await response.json();
        if (data.success) {
            alert('Configuración actualizada');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error actualizando configuración: ' + error.message);
    }
}

// ========== Métricas ==========

async function loadMetrics() {
    try {
        const response = await fetch(`${API_BASE}/metrics/current`);
        const data = await response.json();
        
        if (data.success && data.metrics) {
            const m = data.metrics;
            // Métricas básicas
            document.getElementById('metric-alive').textContent = m.chunkservers_alive || 0;
            document.getElementById('metric-dead').textContent = m.chunkservers_dead || 0;
            document.getElementById('metric-chunks').textContent = m.total_chunks || 0;
            document.getElementById('metric-under-replicated').textContent = m.under_replicated_chunks || 0;
            document.getElementById('metric-files').textContent = m.total_files || 0;
            
            // Throughput (operaciones por segundo)
            const throughput = m.throughput || {};
            const totalThroughput = (throughput.read || 0) + (throughput.write || 0) + (throughput.append || 0);
            document.getElementById('metric-throughput').textContent = totalThroughput.toFixed(2);
            
            // Latencia (promedio y percentiles)
            const latency = m.latency || {};
            const latencyAll = latency.all || {};
            document.getElementById('metric-latency-avg').textContent = 
                latencyAll.avg ? (latencyAll.avg * 1000).toFixed(2) : '-';
            document.getElementById('metric-latency-p95').textContent = 
                latencyAll.p95 ? (latencyAll.p95 * 1000).toFixed(2) : '-';
            document.getElementById('metric-latency-p99').textContent = 
                latencyAll.p99 ? (latencyAll.p99 * 1000).toFixed(2) : '-';
            
            // Tasa de fallos
            document.getElementById('metric-failure-rate').textContent = 
                (m.failure_rate || 0).toFixed(2);
            
            // Re-replicaciones activas
            const activeReplications = m.active_replications || {};
            document.getElementById('metric-active-replications').textContent = 
                activeReplications.count || 0;
            
            // Réplicas obsoletas
            const staleReplicas = m.stale_replicas || {};
            document.getElementById('metric-stale-replicas').textContent = 
                staleReplicas.total_stale_replicas || 0;
            
            // Mostrar detalles adicionales
            showMetricsDetails(m);
        }
    } catch (error) {
        console.error('Error cargando métricas:', error);
    }
}

function showMetricsDetails(metrics) {
    const detailsDiv = document.getElementById('metrics-details');
    const contentDiv = document.getElementById('metrics-details-content');
    
    if (!metrics.throughput && !metrics.chunkserver_load && !metrics.fragmentation) {
        detailsDiv.style.display = 'none';
        return;
    }
    
    detailsDiv.style.display = 'block';
    let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">';
    
    // Throughput por tipo de operación
    if (metrics.throughput) {
        html += '<div><h4>Throughput por Operación</h4><ul>';
        html += `<li>Read: ${(metrics.throughput.read || 0).toFixed(2)} ops/s</li>`;
        html += `<li>Write: ${(metrics.throughput.write || 0).toFixed(2)} ops/s</li>`;
        html += `<li>Append: ${(metrics.throughput.append || 0).toFixed(2)} ops/s</li>`;
        html += '</ul></div>';
    }
    
    // Latencia por tipo de operación
    if (metrics.latency) {
        html += '<div><h4>Latencia por Operación (ms)</h4><ul>';
        ['read', 'write', 'append'].forEach(op => {
            const lat = metrics.latency[op] || {};
            if (lat.avg) {
                html += `<li>${op.charAt(0).toUpperCase() + op.slice(1)}: avg=${(lat.avg * 1000).toFixed(2)}, p95=${(lat.p95 * 1000).toFixed(2)}, p99=${(lat.p99 * 1000).toFixed(2)}</li>`;
            }
        });
        html += '</ul></div>';
    }
    
    // Distribución de carga por chunkserver
    if (metrics.chunkserver_load && Object.keys(metrics.chunkserver_load).length > 0) {
        html += '<div><h4>Carga por ChunkServer</h4><ul>';
        for (const [csId, load] of Object.entries(metrics.chunkserver_load)) {
            const ops = load.operations || {};
            const totalOps = load.total_operations || 0;
            const bytes = (load.bytes_transferred || 0) / (1024 * 1024); // MB
            html += `<li><strong>${csId}</strong>: ${totalOps} ops, ${bytes.toFixed(2)} MB</li>`;
        }
        html += '</ul></div>';
    }
    
    // Fragmentación
    if (metrics.fragmentation) {
        const frag = metrics.fragmentation;
        html += '<div><h4>Fragmentación de Archivos</h4><ul>';
        html += `<li>Archivos totales: ${frag.total_files || 0}</li>`;
        html += `<li>Chunks promedio por archivo: ${(frag.avg_chunks_per_file || 0).toFixed(2)}</li>`;
        html += `<li>Máximo chunks por archivo: ${frag.max_chunks_per_file || 0}</li>`;
        html += '</ul></div>';
    }
    
    // Réplicas obsoletas
    if (metrics.stale_replicas) {
        const stale = metrics.stale_replicas;
        html += '<div><h4>Réplicas Obsoletas</h4><ul>';
        html += `<li>Chunks con réplicas obsoletas: ${stale.chunks_with_stale_replicas || 0}</li>`;
        html += `<li>Total réplicas obsoletas: ${stale.total_stale_replicas || 0}</li>`;
        html += '</ul></div>';
    }
    
    html += '</div>';
    contentDiv.innerHTML = html;
}

// ========== Gráficas ==========

async function generatePerformanceGraph() {
    try {
        const response = await fetch(`${API_BASE}/metrics/graph`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            const display = document.getElementById('graph-display');
            display.innerHTML = `<h3>Gráfica de Rendimiento</h3><img src="${data.url}" alt="Gráfica de rendimiento">`;
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error generando gráfica: ' + error.message);
    }
}

async function generateClusterView() {
    try {
        const response = await fetch(`${API_BASE}/visualization/cluster`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            const display = document.getElementById('graph-display');
            display.innerHTML = `<h3>Vista del Cluster</h3><img src="${data.url}" alt="Vista del cluster">`;
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error generando vista: ' + error.message);
    }
}

async function generateNetworkTopologyImage() {
    try {
        const response = await fetch(`${API_BASE}/visualization/topology`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            const display = document.getElementById('graph-display');
            display.innerHTML = `<h3>Topología de Red</h3><img src="${data.url}" alt="Topología de red">`;
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error generando topología: ' + error.message);
    }
}

async function generateChunkDistributionImage() {
    const filePath = document.getElementById('file-selector').value || null;
    
    try {
        const response = await fetch(`${API_BASE}/visualization/distribution`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const display = document.getElementById('graph-display');
            display.innerHTML = `<h3>Distribución de Chunks</h3><img src="${data.url}" alt="Distribución de chunks">`;
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Error generando distribución: ' + error.message);
    }
}

