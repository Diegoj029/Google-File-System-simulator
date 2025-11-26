"""
Tests básicos para el MasterMetadata.

Verifica operaciones básicas de metadatos.
"""
import unittest
from pathlib import Path
import tempfile
import shutil

from mini_gfs.master.metadata import MasterMetadata
from mini_gfs.common.config import MasterConfig


class TestMasterMetadata(unittest.TestCase):
    """Tests para MasterMetadata"""
    
    def setUp(self):
        """Configuración antes de cada test."""
        # Crear directorio temporal para metadatos
        self.temp_dir = tempfile.mkdtemp()
        config = MasterConfig(
            metadata_dir=self.temp_dir,
            chunk_size=1024 * 1024,  # 1 MB
            replication_factor=3
        )
        self.metadata = MasterMetadata(config)
    
    def tearDown(self):
        """Limpieza después de cada test."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_file(self):
        """Test de creación de archivo."""
        # Crear archivo
        result = self.metadata.create_file("/test.txt")
        self.assertTrue(result)
        
        # Intentar crear el mismo archivo de nuevo (debe fallar)
        result = self.metadata.create_file("/test.txt")
        self.assertFalse(result)
        
        # Verificar que el archivo existe
        file_meta = self.metadata.get_file("/test.txt")
        self.assertIsNotNone(file_meta)
        self.assertEqual(file_meta.path, "/test.txt")
    
    def test_allocate_chunk(self):
        """Test de asignación de chunk."""
        # Crear archivo primero
        self.metadata.create_file("/test.txt")
        
        # Registrar un chunkserver
        self.metadata.register_chunkserver(
            "cs1",
            "http://localhost:8001",
            []
        )
        
        # Asignar chunk
        chunk_handle = self.metadata.allocate_chunk(
            "/test.txt",
            0,
            ["cs1"]
        )
        
        self.assertIsNotNone(chunk_handle)
        
        # Verificar que el chunk existe
        chunk_meta = self.metadata.get_chunk_locations(chunk_handle)
        self.assertIsNotNone(chunk_meta)
        self.assertEqual(len(chunk_meta.replicas), 1)
    
    def test_save_and_load_snapshot(self):
        """Test de guardado y carga de snapshot."""
        # Crear algunos datos
        self.metadata.create_file("/test1.txt")
        self.metadata.create_file("/test2.txt")
        self.metadata.register_chunkserver(
            "cs1",
            "http://localhost:8001",
            []
        )
        
        # Guardar snapshot
        result = self.metadata.save_snapshot()
        self.assertTrue(result)
        
        # Crear nueva instancia y cargar
        config = MasterConfig(
            metadata_dir=self.temp_dir,
            chunk_size=1024 * 1024,
            replication_factor=3
        )
        new_metadata = MasterMetadata(config)
        result = new_metadata.load_snapshot()
        self.assertTrue(result)
        
        # Verificar que los datos se cargaron
        file1 = new_metadata.get_file("/test1.txt")
        file2 = new_metadata.get_file("/test2.txt")
        self.assertIsNotNone(file1)
        self.assertIsNotNone(file2)
        self.assertIn("cs1", new_metadata.chunkservers)


if __name__ == '__main__':
    unittest.main()

