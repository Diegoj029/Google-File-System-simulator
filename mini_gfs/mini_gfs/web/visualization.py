"""
Funciones de visualización para generar gráficas del sistema GFS.

Genera gráficas usando matplotlib para topología de red,
distribución de chunks, y métricas de rendimiento.
"""
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, ConnectionPatch
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import networkx as nx


class VisualizationGenerator:
    """Generador de visualizaciones del sistema GFS."""
    
    def __init__(self, output_dir: str = "output"):
        """
        Inicializa el generador de visualizaciones.
        
        Args:
            output_dir: Directorio donde guardar las gráficas
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_performance_graph(self, metrics_history: List[Dict]) -> Optional[str]:
        """
        Genera gráfico de rendimiento con múltiples métricas.
        
        Args:
            metrics_history: Lista de métricas históricas
        
        Returns:
            Ruta del archivo generado o None si falla
        """
        if not metrics_history:
            return None
        
        try:
            fig, axes = plt.subplots(3, 1, figsize=(12, 10))
            fig.suptitle('Métricas de Rendimiento del Sistema GFS', fontsize=16, fontweight='bold')
            
            timestamps = [m.get('timestamp', '') for m in metrics_history]
            chunkservers_alive = [m.get('chunkservers_alive', 0) for m in metrics_history]
            total_chunks = [m.get('total_chunks', 0) for m in metrics_history]
            under_replicated = [m.get('under_replicated_chunks', 0) for m in metrics_history]
            
            # Gráfico 1: ChunkServers vivos
            axes[0].plot(range(len(timestamps)), chunkservers_alive, 'g-', linewidth=2, marker='o')
            axes[0].set_title('ChunkServers Vivos', fontweight='bold')
            axes[0].set_ylabel('Número de ChunkServers')
            axes[0].grid(True, alpha=0.3)
            axes[0].set_ylim(bottom=0)
            
            # Gráfico 2: Total de chunks
            axes[1].plot(range(len(timestamps)), total_chunks, 'b-', linewidth=2, marker='s')
            axes[1].set_title('Total de Chunks en el Sistema', fontweight='bold')
            axes[1].set_ylabel('Número de Chunks')
            axes[1].grid(True, alpha=0.3)
            axes[1].set_ylim(bottom=0)
            
            # Gráfico 3: Chunks sub-replicados
            axes[2].plot(range(len(timestamps)), under_replicated, 'r-', linewidth=2, marker='^')
            axes[2].set_title('Chunks Sub-replicados', fontweight='bold')
            axes[2].set_xlabel('Tiempo (muestras)')
            axes[2].set_ylabel('Número de Chunks')
            axes[2].grid(True, alpha=0.3)
            axes[2].set_ylim(bottom=0)
            
            plt.tight_layout()
            
            file_path = self.output_dir / 'performance_graph.png'
            plt.savefig(file_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return str(file_path)
            
        except Exception as e:
            print(f"Error generando gráfico de rendimiento: {e}")
            return None
    
    def generate_cluster_view(self, master_state: Dict) -> Optional[str]:
        """
        Genera vista del cluster con distribución de chunks.
        
        Args:
            master_state: Estado del sistema desde el Master
        
        Returns:
            Ruta del archivo generado o None si falla
        """
        try:
            chunkservers = master_state.get('chunkservers', {})
            if not chunkservers:
                return None
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            fig.suptitle('Vista del Cluster GFS', fontsize=16, fontweight='bold')
            
            # Gráfico 1: Distribución de chunks por ChunkServer (barras)
            cs_ids = []
            chunks_counts = []
            colors = []
            
            for cs_id, cs_info in chunkservers.items():
                cs_ids.append(cs_id)
                chunks_count = len(cs_info.get('chunks', []))
                chunks_counts.append(chunks_count)
                # Verde si está vivo, rojo si está muerto
                colors.append('green' if cs_info.get('is_alive', False) else 'red')
            
            bars = ax1.bar(cs_ids, chunks_counts, color=colors, alpha=0.7, edgecolor='black', linewidth=1.5)
            ax1.set_title('Distribución de Chunks por ChunkServer', fontweight='bold')
            ax1.set_xlabel('ChunkServer ID')
            ax1.set_ylabel('Número de Chunks')
            ax1.grid(True, alpha=0.3, axis='y')
            
            # Agregar valores en las barras
            for bar in bars:
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom', fontweight='bold')
            
            # Leyenda
            alive_patch = mpatches.Patch(color='green', label='ChunkServer Vivo')
            dead_patch = mpatches.Patch(color='red', label='ChunkServer Muerto')
            ax1.legend(handles=[alive_patch, dead_patch])
            
            # Gráfico 2: Distribución de réplicas (circular)
            replication_factor = master_state.get('replication_factor', 3)
            chunks = master_state.get('chunks', {})
            
            complete = sum(1 for c in chunks.values() if len(c.get('replicas', [])) >= replication_factor)
            under_replicated = len(chunks) - complete
            
            if len(chunks) > 0:
                sizes = [complete, under_replicated]
                labels = ['Réplicas Completas', 'Sub-replicados']
                colors_pie = ['#2ecc71', '#e74c3c']
                explode = (0.05, 0.1) if under_replicated > 0 else (0, 0)
                
                ax2.pie(sizes, explode=explode, labels=labels, colors=colors_pie,
                       autopct='%1.1f%%', shadow=True, startangle=90, textprops={'fontweight': 'bold'})
                ax2.set_title('Estado de Réplicas', fontweight='bold')
            else:
                ax2.text(0.5, 0.5, 'No hay chunks\nen el sistema', 
                        ha='center', va='center', fontsize=14, fontweight='bold')
                ax2.set_title('Estado de Réplicas', fontweight='bold')
            
            plt.tight_layout()
            
            file_path = self.output_dir / 'cluster_view.png'
            plt.savefig(file_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return str(file_path)
            
        except Exception as e:
            print(f"Error generando vista del cluster: {e}")
            return None
    
    def generate_network_topology(self, topology_data: Dict) -> Optional[str]:
        """
        Genera visualización de la topología de red.
        
        Args:
            topology_data: Datos de topología del sistema
        
        Returns:
            Ruta del archivo generado o None si falla
        """
        try:
            fig, ax = plt.subplots(figsize=(14, 10))
            ax.set_xlim(-1.5, 1.5)
            ax.set_ylim(-1.5, 1.5)
            ax.axis('off')
            ax.set_title('Topología del Sistema GFS', fontsize=18, fontweight='bold', pad=20)
            
            master = topology_data.get('master', {})
            chunkservers = topology_data.get('chunkservers', [])
            
            # Dibujar Master en el centro
            master_x, master_y = 0, 0
            master_color = '#3498db'  # Azul
            master_circle = plt.Circle((master_x, master_y), 0.15, color=master_color, 
                                      zorder=3, edgecolor='black', linewidth=2)
            ax.add_patch(master_circle)
            ax.text(master_x, master_y, 'M', ha='center', va='center', 
                   fontsize=16, fontweight='bold', color='white', zorder=4)
            
            # Etiqueta del Master
            ax.text(master_x, master_y - 0.3, 'Master\n(Coordinador Central)', 
                   ha='center', va='top', fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))
            
            # Dibujar ChunkServers en círculo alrededor del Master
            num_cs = len(chunkservers)
            if num_cs > 0:
                angle_step = 2 * np.pi / num_cs
                radius = 0.8
                
                for i, cs in enumerate(chunkservers):
                    angle = i * angle_step - np.pi / 2  # Empezar arriba
                    cs_x = radius * np.cos(angle)
                    cs_y = radius * np.sin(angle)
                    
                    # Color según estado
                    if cs.get('status') == 'alive':
                        cs_color = '#2ecc71'  # Verde
                    else:
                        cs_color = '#e74c3c'  # Rojo
                    
                    # Dibujar ChunkServer
                    cs_circle = plt.Circle((cs_x, cs_y), 0.12, color=cs_color,
                                          zorder=3, edgecolor='black', linewidth=2)
                    ax.add_patch(cs_circle)
                    ax.text(cs_x, cs_y, cs.get('id', 'CS')[-1], ha='center', va='center',
                           fontsize=14, fontweight='bold', color='white', zorder=4)
                    
                    # Línea de conexión Master -> ChunkServer
                    connection = ConnectionPatch((master_x, master_y), (cs_x, cs_y), 
                                                "data", "data",
                                                arrowstyle="->", shrinkA=5, shrinkB=5,
                                                mutation_scale=20, fc="gray", ec="gray",
                                                linewidth=2, alpha=0.6, zorder=1)
                    ax.add_patch(connection)
                    
                    # Etiqueta del ChunkServer
                    label_y = cs_y - 0.25 if cs_y >= 0 else cs_y + 0.25
                    chunks_count = cs.get('chunks_count', 0)
                    status_text = 'Vivo' if cs.get('status') == 'alive' else 'Muerto'
                    ax.text(cs_x, label_y, f"{cs.get('id', 'CS')}\n{chunks_count} chunks\n{status_text}",
                           ha='center', va='top' if cs_y >= 0 else 'bottom',
                           fontsize=9, fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', 
                                   facecolor='lightgreen' if cs.get('status') == 'alive' else 'lightcoral',
                                   alpha=0.8))
            
            # Leyenda
            legend_elements = [
                plt.Circle((0, 0), 0.1, color='#3498db', label='Master'),
                plt.Circle((0, 0), 0.1, color='#2ecc71', label='ChunkServer Vivo'),
                plt.Circle((0, 0), 0.1, color='#e74c3c', label='ChunkServer Muerto'),
                plt.Line2D([0], [0], color='gray', linewidth=2, label='Conexión (Heartbeat)')
            ]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=10, framealpha=0.9)
            
            # Información adicional
            info_text = f"Total ChunkServers: {num_cs}\n"
            info_text += f"ChunkServers Vivos: {sum(1 for cs in chunkservers if cs.get('status') == 'alive')}"
            ax.text(-1.4, -1.4, info_text, fontsize=10, 
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.8))
            
            plt.tight_layout()
            
            file_path = self.output_dir / 'network_topology.png'
            plt.savefig(file_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return str(file_path)
            
        except Exception as e:
            print(f"Error generando topología de red: {e}")
            return None
    
    def generate_chunk_distribution(self, distribution_data: Dict, file_path: Optional[str] = None) -> Optional[str]:
        """
        Genera visualización de distribución de chunks.
        
        Args:
            distribution_data: Datos de distribución de chunks
            file_path: Ruta del archivo específico (None para vista general)
        
        Returns:
            Ruta del archivo generado o None si falla
        """
        try:
            chunks = distribution_data.get('chunks', [])
            summary = distribution_data.get('summary', {})
            chunkservers_stats = summary.get('chunkservers_stats', {})
            
            if not chunks:
                # Crear gráfico vacío
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.text(0.5, 0.5, 'No hay chunks en el sistema', 
                       ha='center', va='center', fontsize=16, fontweight='bold')
                ax.set_title('Distribución de Chunks', fontsize=14, fontweight='bold')
                ax.axis('off')
                
                file_path_out = self.output_dir / 'chunk_distribution.png'
                plt.savefig(file_path_out, dpi=150, bbox_inches='tight')
                plt.close()
                return str(file_path_out)
            
            if file_path:
                # Vista por archivo específico
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
                fig.suptitle(f'Distribución de Chunks: {file_path}', fontsize=16, fontweight='bold')
                
                # Gráfico 1: Distribución por ChunkServer (barras)
                cs_ids = list(chunkservers_stats.keys())
                chunks_counts = [stats['total_chunks'] for stats in chunkservers_stats.values()]
                colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6'][:len(cs_ids)]
                
                bars = ax1.bar(cs_ids, chunks_counts, color=colors, alpha=0.7, edgecolor='black', linewidth=1.5)
                ax1.set_title('Chunks por ChunkServer', fontweight='bold')
                ax1.set_xlabel('ChunkServer ID')
                ax1.set_ylabel('Número de Chunks')
                ax1.grid(True, alpha=0.3, axis='y')
                
                for bar in bars:
                    height = bar.get_height()
                    ax1.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height)}', ha='center', va='bottom', fontweight='bold')
                
                # Gráfico 2: Visualización de réplicas
                ax2.axis('off')
                ax2.set_title('Mapa de Réplicas', fontweight='bold', pad=10)
                
                # Crear grafo de réplicas
                try:
                    G = nx.Graph()
                    
                    # Agregar nodos (chunks y chunkservers)
                    for chunk in chunks:
                        chunk_handle_short = chunk['handle'][:8]
                        G.add_node(chunk_handle_short, node_type='chunk')
                        for cs_id in chunk['chunkservers']:
                            G.add_node(cs_id, node_type='chunkserver')
                            G.add_edge(chunk_handle_short, cs_id)
                    
                    if len(G.nodes()) > 0:
                        # Layout
                        pos = nx.spring_layout(G, k=1, iterations=50)
                        
                        # Dibujar nodos
                        chunk_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'chunk']
                        cs_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'chunkserver']
                        
                        nx.draw_networkx_nodes(G, pos, nodelist=chunk_nodes, node_color='#3498db',
                                              node_size=500, alpha=0.8, ax=ax2)
                        nx.draw_networkx_nodes(G, pos, nodelist=cs_nodes, node_color='#2ecc71',
                                              node_size=1000, alpha=0.8, ax=ax2)
                        
                        # Dibujar aristas
                        nx.draw_networkx_edges(G, pos, alpha=0.5, width=2, ax=ax2)
                        
                        # Etiquetas
                        labels = {n: n[:4] for n in G.nodes()}
                        nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight='bold', ax=ax2)
                    else:
                        ax2.text(0.5, 0.5, 'No hay chunks\npara visualizar', 
                                ha='center', va='center', fontsize=12, fontweight='bold')
                except Exception as e:
                    ax2.text(0.5, 0.5, f'Error generando grafo:\n{str(e)}', 
                            ha='center', va='center', fontsize=10)
                
            else:
                # Vista general
                fig, ax = plt.subplots(figsize=(14, 8))
                fig.suptitle('Distribución General de Chunks', fontsize=16, fontweight='bold')
                
                # Agrupar chunks por archivo
                files_chunks = {}
                for chunk in chunks:
                    file = chunk.get('file_path', 'unknown')
                    if file not in files_chunks:
                        files_chunks[file] = {}
                    for cs_id in chunk['chunkservers']:
                        files_chunks[file][cs_id] = files_chunks[file].get(cs_id, 0) + 1
                
                # Gráfico de barras apiladas
                cs_ids = sorted(list(chunkservers_stats.keys()))
                file_names = list(files_chunks.keys())
                
                if file_names:
                    bottom = np.zeros(len(cs_ids))
                    colors_map = plt.cm.Set3(np.linspace(0, 1, len(file_names)))
                    
                    for i, file_name in enumerate(file_names):
                        values = [files_chunks[file_name].get(cs_id, 0) for cs_id in cs_ids]
                        ax.bar(cs_ids, values, bottom=bottom, label=file_name[:30],
                              color=colors_map[i], alpha=0.8, edgecolor='black', linewidth=1)
                        bottom += values
                    
                    ax.set_xlabel('ChunkServer ID', fontweight='bold')
                    ax.set_ylabel('Número de Chunks', fontweight='bold')
                    ax.set_title('Distribución de Chunks por Archivo y ChunkServer', fontweight='bold')
                    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
                    ax.grid(True, alpha=0.3, axis='y')
                else:
                    ax.text(0.5, 0.5, 'No hay archivos en el sistema', 
                           ha='center', va='center', fontsize=14, fontweight='bold')
                    ax.axis('off')
            
            plt.tight_layout()
            
            file_path_out = self.output_dir / 'chunk_distribution.png'
            plt.savefig(file_path_out, dpi=150, bbox_inches='tight')
            plt.close()
            
            return str(file_path_out)
            
        except Exception as e:
            print(f"Error generando distribución de chunks: {e}")
            import traceback
            traceback.print_exc()
            return None

