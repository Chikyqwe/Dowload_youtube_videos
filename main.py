from flask import Flask, request, jsonify,Response,send_file, render_template, abort
import os
import threading
import uuid
import time
import queue
import tempfile
import subprocess
import shlex
from youtubesearchpython import VideosSearch
import requests
from urllib.parse import quote

app = Flask(__name__)

# Carpeta temporal para descargas
DOWNLOAD_DIR = tempfile.mkdtemp(prefix="downloads_")
print(f"[INFO] Carpeta temporal: {DOWNLOAD_DIR}")

# Estados de descarga y colas
download_progress = {}
progress_lock = threading.Lock()
download_queue = queue.Queue()
queue_list_lock = threading.Lock()
queued_ids = []

# Función para ejecutar yt-dlp binario
def download_worker(url, fmt, download_id):
    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')

    # Comando según formato
    if fmt == 'mp3':
        cmd = f'./yt-dlp -x --audio-format mp3 -o "{output_template}" --no-playlist "{url}"'
    else:
        cmd = f'./yt-dlp -f bestvideo+bestaudio/best -o "{output_template}" --no-playlist "{url}"'

    try:
        process = subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        # Parsear progreso aproximado
        for line in process.stdout:
            if '%' in line:
                try:
                    percent = int(line.split('%')[0].split()[-1])
                    with progress_lock:
                        download_progress[download_id] = percent
                        print(f"[{download_id}] Progreso: {percent}%")
                except:
                    pass

        process.wait()

        # Buscar archivo descargado
        files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR)]
        files = [f for f in files if os.path.isfile(f)]
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

        if files:
            filename = files[0]
            with progress_lock:
                download_progress[f"{download_id}_file"] = filename
                download_progress[f"{download_id}_name"] = os.path.basename(filename)
                download_progress[download_id] = 100
                print(f"[{download_id}] Archivo listo: {filename}")
        else:
            with progress_lock:
                download_progress[download_id] = -1
                print(f"[{download_id}] Archivo no válido")

    except Exception as e:
        with progress_lock:
            download_progress[download_id] = -1
        print(f"[{download_id}] Error: {e}")

# Worker de la cola
def queue_worker():
    while True:
        job = download_queue.get()
        if job is None:
            break
        url, fmt, download_id = job
        print(f"[QUEUE] Empezando descarga {download_id}")
        download_worker(url, fmt, download_id)
        with queue_list_lock:
            if download_id in queued_ids:
                queued_ids.remove(download_id)
        download_queue.task_done()
        print(f"[QUEUE] Descarga {download_id} finalizada")

# Limpieza de archivos antiguos o excesivos
def cleanup_old_files():
    while True:
        try:
            files = [
                (os.path.join(DOWNLOAD_DIR, f), os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)))
                for f in os.listdir(DOWNLOAD_DIR)
                if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))
            ]
            now = time.time()
            files.sort(key=lambda x: x[1])

            for fpath, mtime in files:
                if now - mtime > 300:
                    os.remove(fpath)
                    print(f"[CLEANUP] Borrado por antigüedad: {fpath}")

            if len(files) > 20:
                for fpath, _ in files[:len(files) - 20]:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                        print(f"[CLEANUP] Borrado por exceso: {fpath}")

        except Exception as e:
            print(f"[CLEANUP] Error: {e}")

        time.sleep(120)

# Threads
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

# Rutas Flask
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    videos = VideosSearch(query, limit=20).result().get('result', [])
    results = [{
        'title': v['title'],
        'url': v['link'],
        'thumbnail': v['thumbnails'][0]['url']
    } for v in videos]

    return jsonify(results)

@app.route('/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', 'mp4')

    if not url:
        return abort(400, 'URL requerida')

    download_id = str(uuid.uuid4())
    with progress_lock:
        download_progress[download_id] = 0

    with queue_list_lock:
        queued_ids.append(download_id)
    download_queue.put((url, fmt, download_id))

    return jsonify({'download_id': download_id, 'position_in_queue': queued_ids.index(download_id) + 1})

@app.route('/queue')
def queue_status():
    with queue_list_lock:
        queue_info = []
        for idx, did in enumerate(queued_ids, 1):
            with progress_lock:
                prog = download_progress.get(did, 0)
            estado = "En cola" if prog == 0 else f"Progreso: {prog}%"
            queue_info.append({'download_id': did, 'position': idx, 'status': estado})
    return jsonify(queue_info)

@app.route('/progress')
def progress():
    download_id = request.args.get('id')
    if not download_id:
        return jsonify({'error': 'ID requerido'}), 400

    with progress_lock:
        prog = download_progress.get(download_id)
        if prog is None:
            return jsonify({'error': 'ID inválido'}), 404

    return jsonify({'progress': prog})

@app.route('/get_file')
def get_file():
    download_id = request.args.get('id')
    if not download_id:
        return jsonify({'error': 'ID requerido'}), 400

    with progress_lock:
        prog = download_progress.get(download_id)
        filename = download_progress.get(f"{download_id}_file")
        real_name = download_progress.get(f"{download_id}_name")

    if prog != 100 or not filename or not real_name:
        return jsonify({'error': 'Archivo no disponible'}), 404

    if not os.path.exists(filename):
        return jsonify({'error': 'Archivo no encontrado en disco'}), 404

    ext = os.path.splitext(real_name)[1].lower()
    if ext not in ['.mp3', '.mp4', '.webm']:
        return jsonify({'error': 'Formato no permitido'}), 400

    try:
        return send_file(filename, as_attachment=True, download_name=real_name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/video_url')
def video_url():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL requerida'}), 400

    # Obtener solo formatos MP4 progresivos (video + audio juntos)
    cmd = f'./yt-dlp -f "best[ext=mp4]" --get-url "{url}"'

    try:
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=True)
        direct_url = result.stdout.strip()
        return jsonify({'direct_url': direct_url})
    except subprocess.CalledProcessError as e:
        return jsonify({'error': 'No se pudo obtener la URL', 'details': e.stderr}), 500


@app.route('/video-player')
def video_player_proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL requerida'}), 400

    try:
        # Detectamos si es un m3u8
        if url.endswith('.m3u8'):
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return jsonify({'error': 'No se pudo obtener el m3u8'}), 502

            playlist = r.text
            modified_lines = []

            for line in playlist.splitlines():
                line = line.strip()
                # Reescribimos solo las líneas que no son comentarios y son URLs
                if line and not line.startswith('#') and line.startswith('http'):
                    # Escapamos la URL original
                    proxied_url = f"/video-player?url={quote(line, safe='')}"
                    modified_lines.append(proxied_url)
                else:
                    modified_lines.append(line)

            modified_playlist = "\n".join(modified_lines)
            return Response(modified_playlist, content_type='application/vnd.apple.mpegurl')

        else:
            # Si es un TS u otro recurso, lo servimos como stream
            r = requests.get(url, stream=True, timeout=10)
            if r.status_code != 200:
                return jsonify({'error': 'No se pudo obtener el recurso'}), 502

            return Response(
                r.iter_content(chunk_size=1024*1024),
                content_type=r.headers.get('content-type', 'application/octet-stream'),
                status=r.status_code
            )

    except Exception as e:
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5555))
    app.run(debug=False, host='0.0.0.0', port=port)
