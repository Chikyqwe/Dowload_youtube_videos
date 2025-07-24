from flask import Flask, request, jsonify, send_file, render_template, abort
from youtubesearchpython import VideosSearch
import yt_dlp
import os
import threading
import uuid
import time
import queue

app = Flask(__name__)

# Ruta de descargas
DOWNLOAD_DIR = './'

def leer_version():
    try:
        with open("version.ve", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Estado de descargas: {id: progreso, id_file: ruta, id_name: nombre real}
download_progress = {}
progress_lock = threading.Lock()

# Cola para trabajos de descarga
download_queue = queue.Queue()
queue_list_lock = threading.Lock()
queued_ids = []  # Para seguimiento ordenado y mostrar la lista

def progress_hook(d, download_id):
    with progress_lock:
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent = int(downloaded / total * 100)
                download_progress[download_id] = percent
                print(f"[{download_id}] Progreso: {percent}%")
        elif d['status'] == 'finished':
            print(f"[{download_id}] Descarga finalizada")
            download_progress[download_id] = 100

def download_worker(url, fmt, download_id):
    output_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'progress_hooks': [lambda d: progress_hook(d, download_id)]
    }

    if fmt == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }],
            'outtmpl': output_template
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if fmt == 'mp3':
                filename = os.path.splitext(filename)[0] + '.mp3'

            filename = os.path.abspath(filename)
            basename = os.path.basename(filename)  # nombre real con extensión

            # Esperar archivo estable
            wait_time, stable_checks = 0, 0
            last_size = -1

            while wait_time < 20:
                if os.path.exists(filename):
                    current_size = os.path.getsize(filename)
                    if current_size == last_size:
                        stable_checks += 1
                    else:
                        stable_checks = 0
                    if stable_checks >= 3:
                        break
                    last_size = current_size
                time.sleep(0.5)
                wait_time += 0.5

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                with progress_lock:
                    download_progress[f"{download_id}_file"] = filename
                    download_progress[f"{download_id}_name"] = basename
                    download_progress[download_id] = 100
                    print(f"[{download_id}] Archivo listo: {filename}")
            else:
                with progress_lock:
                    download_progress[download_id] = -1
                    print(f"[{download_id}] Error: archivo no válido")

    except Exception as e:
        with progress_lock:
            download_progress[download_id] = -1
        print(f"[{download_id}] Error: {e}")

def queue_worker():
    while True:
        job = download_queue.get()
        if job is None:
            break  # Permite parar el hilo si es necesario
        url, fmt, download_id = job
        print(f"[QUEUE] Empezando descarga {download_id}")
        download_worker(url, fmt, download_id)
        with queue_list_lock:
            if download_id in queued_ids:
                queued_ids.remove(download_id)
        download_queue.task_done()
        print(f"[QUEUE] Descarga {download_id} finalizada")

# Iniciar el hilo trabajador en background (daemon=True para que no bloquee al cerrar)
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()

@app.route('/')
def index():
    return render_template('index.html', version=leer_version())

@app.route('/version')
def version():
    return leer_version()

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
        print(f"[{download_id}] Archivo no encontrado: {filename}")
        return jsonify({'error': 'Archivo no encontrado en disco'}), 404

    ext = os.path.splitext(real_name)[1].lower()
    if ext not in ['.mp3', '.mp4', 'webm']:
        return jsonify({'error': 'Formato no permitido'}), 400

    return send_file(filename, as_attachment=True, download_name=real_name)

@app.route('/video_url')
def video_url():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL'}), 400

    try:
        opts = {'quiet': True, 'skip_download': True, 'format': 'mp4'}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            for f in info.get('formats', []):
                if f.get('ext') == 'mp4' and f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                    return jsonify({'direct_url': f['url']})
        return jsonify({'error': 'No se encontró URL directa'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5555))
    app.run(debug=False, host='0.0.0.0', port=port)
