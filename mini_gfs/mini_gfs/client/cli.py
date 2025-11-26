"""
CLI (Command Line Interface) del Cliente.

Proporciona comandos para interactuar con el mini-GFS.
"""
import argparse
import sys
from .client_api import ClientAPI


def main():
    """Función principal del CLI."""
    parser = argparse.ArgumentParser(
        description="Cliente CLI para mini-GFS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s create /test.txt
  %(prog)s write /test.txt 0 "Hello, World!"
  %(prog)s read /test.txt 0 12
  %(prog)s append /test.txt "More data"
  %(prog)s ls /test.txt
        """
    )
    
    parser.add_argument(
        '--master',
        default='http://localhost:8000',
        help='Dirección del Master (default: http://localhost:8000)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponibles')
    
    # Comando create
    create_parser = subparsers.add_parser('create', help='Crear un nuevo archivo')
    create_parser.add_argument('path', help='Ruta del archivo a crear')
    
    # Comando write
    write_parser = subparsers.add_parser('write', help='Escribir datos en un archivo')
    write_parser.add_argument('path', help='Ruta del archivo')
    write_parser.add_argument('offset', type=int, help='Offset en bytes')
    write_parser.add_argument('data', help='Datos a escribir')
    
    # Comando read
    read_parser = subparsers.add_parser('read', help='Leer datos de un archivo')
    read_parser.add_argument('path', help='Ruta del archivo')
    read_parser.add_argument('offset', type=int, help='Offset en bytes')
    read_parser.add_argument('length', type=int, help='Número de bytes a leer')
    
    # Comando append
    append_parser = subparsers.add_parser('append', help='Añadir datos al final de un archivo')
    append_parser.add_argument('path', help='Ruta del archivo')
    append_parser.add_argument('data', help='Datos a añadir')
    
    # Comando ls
    ls_parser = subparsers.add_parser('ls', help='Listar información de un archivo')
    ls_parser.add_argument('path', help='Ruta del archivo')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Crear cliente
    client = ClientAPI(master_address=args.master)
    
    # Ejecutar comando
    if args.command == 'create':
        success = client.create_file(args.path)
        if success:
            print(f"Archivo {args.path} creado exitosamente")
        else:
            print(f"Error: No se pudo crear el archivo {args.path}")
            sys.exit(1)
    
    elif args.command == 'write':
        data_bytes = args.data.encode('utf-8')
        success = client.write(args.path, args.offset, data_bytes)
        if success:
            print(f"Datos escritos en {args.path} en offset {args.offset}")
        else:
            print(f"Error: No se pudieron escribir datos en {args.path}")
            sys.exit(1)
    
    elif args.command == 'read':
        data = client.read(args.path, args.offset, args.length)
        if data is not None:
            try:
                # Intentar decodificar como texto
                text = data.decode('utf-8')
                print(text)
            except UnicodeDecodeError:
                # Si no es texto, mostrar como bytes
                print(f"Datos (hex): {data.hex()}")
                print(f"Datos (bytes): {len(data)} bytes")
        else:
            print(f"Error: No se pudieron leer datos de {args.path}")
            sys.exit(1)
    
    elif args.command == 'append':
        data_bytes = args.data.encode('utf-8')
        success = client.append(args.path, data_bytes)
        if success:
            print(f"Datos añadidos a {args.path}")
        else:
            print(f"Error: No se pudieron añadir datos a {args.path}")
            sys.exit(1)
    
    elif args.command == 'ls':
        file_info = client.get_file_info(args.path)
        if file_info:
            print(f"Archivo: {file_info['path']}")
            print(f"Chunks: {len(file_info['chunk_handles'])}")
            print("\nInformación de chunks:")
            for i, chunk_info in enumerate(file_info.get('chunks_info', [])):
                print(f"  Chunk {i}:")
                print(f"    Handle: {chunk_info['chunk_handle']}")
                print(f"    Tamaño: {chunk_info['size']} bytes")
                print(f"    Réplicas: {len(chunk_info['replicas'])}")
                print(f"    Primary: {chunk_info['primary_id']}")
                for j, replica in enumerate(chunk_info['replicas']):
                    print(f"      Réplica {j+1}: {replica['chunkserver_id']} @ {replica['address']}")
        else:
            print(f"Error: Archivo {args.path} no encontrado")
            sys.exit(1)


if __name__ == '__main__':
    main()

