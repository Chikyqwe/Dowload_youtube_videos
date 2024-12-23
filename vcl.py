import os
import time
from flask import Flask, render_template_string, request, send_file
import yt_dlp
from pydub import AudioSegment
import threading
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse
from urllib.parse import parse_qs
import re

app = Flask(__name__)
socketio = SocketIO(app)

# Variable global para llevar el número de los archivos
video_counter = 1

# Lista para almacenar los archivos procesados
processed_files = []

# Función para eliminar el parámetro 'list' de la URL (si existe)
def remove_list_from_url(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if 'list' in query_params:
        query_params.pop('list')
        parsed_url = parsed_url._replace(query=urlencode(query_params, doseq=True))
        return urlunparse(parsed_url)
    return url

# Función para obtener el título del video y eliminar paréntesis
def get_video_title(url):
    ydl_opts = {
        'quiet': True,  # Para suprimir la salida de yt-dlp
        'force_generic_extractor': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get('title', 'video_sin_titulo')
            # Eliminar paréntesis y su contenido
            title = re.sub(r'\(.*?\)', '', title)  # Esto elimina cualquier texto entre paréntesis
            title = title.strip()  # Eliminar espacios adicionales
            return title
    except Exception as e:
        return f"Error al obtener el título: {str(e)}"

# Función para descargar el video
def download_video(url):
    global video_counter
    url = remove_list_from_url(url)
    video_title = get_video_title(url)
    
    # Configuración de yt-dlp con el nombre del archivo usando el título
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{video_title}.%(ext)s',  # Usar el título como nombre del archivo
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        video_counter += 1  # Incrementar el contador después de cada descarga
        return f'{video_title}.mp4'  # Devolver el nombre del archivo descargado
    except Exception as e:
        return f"Error al descargar el video: {str(e)}"

# Función para convertir de mp4 a mp3
def mp4_to_mp3(input_file, output_file):
    try:
        audio = AudioSegment.from_file(input_file, format="mp4")
        audio.export(output_file, format="mp3")
        os.remove(input_file)
        return output_file
    except Exception as e:
        return f"Error al convertir el archivo a mp3: {str(e)}"

# Función para eliminar el archivo después de un retraso
def delete_file_after_delay(file_path, delay=30):
    time.sleep(delay)
    if os.path.exists(file_path):
        os.remove(file_path)

# Función para leer las URLs desde un archivo
def read_urls_from_file(file_path):
    with open(file_path, 'r') as file:
        urls = file.readlines()
    return [url.strip() for url in urls if url.strip()]  # Eliminar espacios y líneas vacías

# Función para obtener el contenido del archivo list_ur.cfg
def get_list_ur_content():
    if os.path.exists('list_ur.cfg'):
        with open('list_ur.cfg', 'r') as file:
            return file.read()
    return ""

# Función para guardar contenido en list_ur.cfg
def save_list_ur_content(content):
    with open('list_ur.cfg', 'w') as file:
        file.write(content)

# Función que maneja la conversión y agrega el archivo procesado a la lista
def process_video_file(url):
    video_path = download_video(url)
    if "Error" in video_path:
        socketio.emit('download_error', {'message': video_path})
        return

    input_path = video_path
    output_path = os.path.splitext(input_path)[0] + ".mp3"
    output_mp3 = mp4_to_mp3(input_path, output_path)
    
    if output_mp3.endswith('.mp3'):
        processed_files.append(output_mp3)
        socketio.emit('file_ready', {'file': output_mp3})
    else:
        socketio.emit('download_error', {'message': f"Error al convertir el archivo: {output_mp3}"})

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'video_url' in request.form:  # Si es el formulario normal con URL
            video_url = request.form['video_url']
            if video_url:
                # Iniciar un hilo para manejar la conversión y envío del archivo
                threading.Thread(target=process_video_file, args=(video_url,)).start()
                return render_template_string("""
                    <html>
                    <body>
                            <script type="text/javascript">
                                 alert('El archivo está siendo procesado. Por favor espere.');
                                 window.location.href = '/';
                            </script>
                    </body>
                    </html>
                """)

        elif 'load_urls' in request.form:  # Si es el botón para leer URLs desde el archivo
            # Leer las URLs desde el archivo list_ur.cfg
            urls = read_urls_from_file('list_ur.cfg')
            if urls:
                # Iniciar hilos para procesar cada archivo
                for url in urls:
                    threading.Thread(target=process_video_file, args=(url,)).start()

                return render_template_string("""
                    <html>
                    <body>
                            <script type="text/javascript">
                                 alert('Los archivos están siendo procesados. Por favor espere.');
                                 window.location.href = '/';
                            </script>
                    </body>
                    </html>
                """)
            else:
                return render_template_string("""
                    <html>
                    <body>
                        <h1>Error</h1>
                        <p>No se encontraron URLs en el archivo list_ur.cfg.</p>
                        <a href="/">Volver</a>
                    </body>
                    </html>
                """)

        elif 'edit_list' in request.form:  # Si es el botón para editar el archivo list_ur.cfg
            new_content = request.form.get('list_content', '')
            save_list_ur_content(new_content)
            return render_template_string("""
                <html>
                <body>
                    <h1>Archivo guardado exitosamente</h1>
                    <a href="/">Volver</a>
                </body>
                </html>
            """)

    # Mostrar el contenido actual de list_ur.cfg en el formulario de edición
    current_content = get_list_ur_content()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Descargador de Videos YouTube</title>
        <script src="https://cdn.socket.io/4.0.1/socket.io.min.js"></script>
        <script type="text/javascript">
            var socket = io.connect('http://' + document.domain + ':' + location.port);

            socket.on('file_ready', function(data) {
                alert("El archivo está listo para descargarse: " + data.file);
                window.location.href = '/download/' + data.file;
            });

            socket.on('download_error', function(data) {
                alert("Hubo un error: " + data.message);
            });
        </script>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f4f4f9;
                padding: 20px;
                text-align: center;
            }
            .container {
                width: 100%;
                max-width: 500px;
                margin: 0 auto;
                background-color: #ffffff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
            }
            input[type="text"] {
                width: 90%;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            textarea {
                width: 90%;
                height: 150px;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            button {
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            button:hover {
                background-color: #45a049;
            }
        </style>
    </head>
    </head>
    <body>
        <div class="container">
            <h1>Descargador de Videos YouTube</h1>
            <form action="/" method="POST">
                <input type="text" id="video_url" name="video_url" placeholder="Inserte la URL del video" required>
                <button type="submit">Descargar MP3</button>
            </form>
            <form action="/" method="POST" style="margin-top: 20px;">
                <button type="submit" name="load_urls">Cargar y Descargar desde list_ur.cfg</button>
            </form>
            <form action="/" method="POST" style="margin-top: 20px;">
                <textarea name="list_content">{{ current_content }}</textarea>
                <button type="submit" name="edit_list">Guardar Cambios</button>
            </form>
        </div>
    </body>
    </html>
    """, current_content=current_content)

@app.route('/download/<filename>')
def download(filename):
    # Asegurarse de que el archivo esté disponible antes de enviarlo
    if filename in processed_files:
        return send_file(filename, as_attachment=True)
    else:
        return "Archivo no encontrado."

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5642))
    socketio.run(app, host="0.0.0.0", port=port)


