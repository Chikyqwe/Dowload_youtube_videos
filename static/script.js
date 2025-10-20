let currentUrl = "";
let downloadModal = null;
let videoModal = null;
let modalLocked = false; // 🔒 Controla si se puede cerrar el modal

// Mostrar modal de descarga
function openModal(url) {
  currentUrl = url;
  downloadModal = document.getElementById("modal-download");
  downloadModal.classList.add("show");
  resetProgress();
  setButtonState(false, "Iniciar descarga");
  modalLocked = false;

  document.getElementById("start-download").onclick = () => iniciarDescarga(currentUrl);
}

// Cerrar modal de descarga
function closeModal() {
  if (downloadModal) {
    downloadModal.classList.remove("show");
    resetProgress();
  }
}

// Resetear barra de progreso
function resetProgress() {
  document.getElementById("progress").style.width = "0%";
}

// Cambia estado y texto del botón de descarga
function setButtonState(disabled, text) {
  const btn = document.getElementById("start-download");
  btn.disabled = disabled;
  btn.textContent = text;
}

// Iniciar descarga con seguimiento
async function iniciarDescarga(url) {
  const formato = document.getElementById("formato").value;
  setButtonState(true, "Iniciando descarga...");
  modalLocked = true;

  try {
    const res = await fetch(`/download?url=${encodeURIComponent(url)}&format=${formato}`);
    const data = await res.json();
    if (!data.download_id) throw new Error("Fallo al iniciar descarga");

    trackProgress(data.download_id);
  } catch (e) {
    alert("Error iniciando la descarga");
    console.error(e);
    setButtonState(false, "Iniciar descarga");
    modalLocked = false;
  }
}

// Hacer seguimiento del progreso y descargar el archivo
async function trackProgress(downloadId) {
  const progressEl = document.getElementById("progress");

  const poll = async () => {
    try {
      const res = await fetch(`/progress?id=${downloadId}`);
      const data = await res.json();

      if (data.progress >= 0) {
        setButtonState(true, "Descargando");
        const scaledProgress = Math.min(data.progress * 0.6, 60);
        progressEl.style.width = `${scaledProgress}%`;
      }

      if (data.progress === 100) {
        return attemptDownload(downloadId);
      }

      if (data.progress === -1) {
        throw new Error("Fallo en la descarga");
      }

      setTimeout(poll, 1000);
    } catch (e) {
      alert("Error en la descarga");
      console.error(e);
      setButtonState(false, "Iniciar descarga");
      modalLocked = false;
    }
  };

  poll();
}

// Intentar descarga con reintentos
async function attemptDownload(downloadId) {
  const progressEl = document.getElementById("progress");
  let attempts = 0;
  const maxAttempts = 12;

  while (attempts < maxAttempts) {
    try {
      const res = await fetch(`/get_file?id=${downloadId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      if (blob.size === 0) throw new Error("El archivo descargado está vacío.");

      const filename = extractFilenameFromHeader(res.headers.get('Content-Disposition') || '');
      const url = window.URL.createObjectURL(new Blob([blob], { type: blob.type || "application/octet-stream" }));

      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      progressEl.style.width = `100%`;
      setButtonState(true, "Espere por favor...");
      setTimeout(() => {
        setButtonState(false, "Iniciar descarga");
        modalLocked = false; // 🔓 desbloquear
        closeModal();
      }, 2000);

      return;
    } catch (e) {
      console.warn(`Intento ${attempts + 1} fallido`, e);
      attempts++;
      await new Promise(r => setTimeout(r, 5000));
    }
  }

  setButtonState(false, "Iniciar descarga");
  alert("No se pudo descargar el archivo tras varios intentos.");
  modalLocked = false;
}

function extractFilenameFromHeader(header) {
  const match = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(header);
  if (match != null && match[1]) {
    return match[1].replace(/['"]/g, '');
  }
  return `archivo-${Date.now()}`;
}

// Buscar videos
async function buscar() {
  const q = document.getElementById("query").value.trim();
  if (!q) return alert("Por favor, escribe algo para buscar.");

  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error("Error en la respuesta del servidor");

    const videos = await res.json();
    const container = document.getElementById("resultados");
    container.innerHTML = videos.length
      ? ""
      : "<p>No se encontraron resultados.</p>";

    videos.forEach(({ title, url, thumbnail }) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="media-container">
          <img src="${thumbnail}" alt="Miniatura video" loading="lazy" />
        </div>
        <h3>${title}</h3>
        <div class="buttons-container">
          <button class="btn-download" onclick="openModal('${url}')">Descargar</button>
          <button class="btn-play" onclick="reproducirVideo('${url}')">Reproducir</button>
        </div>`;
      container.appendChild(card);
    });
  } catch (e) {
    alert("Error al buscar videos. Intenta de nuevo más tarde.");
    console.error(e);
  }
}

// Obtener URL real y reproducir video
async function reproducirVideo(urlVideo) {
  const modal = document.getElementById('modal-video');
  const video = document.getElementById('video-player');
  const loader = document.getElementById('video-loader');

  // Mostrar modal con loader
  modal.classList.add('show');
  loader.style.display = 'flex';
  video.style.display = 'none';
  video.src = "";
  modalLocked = true;

  try {
    // Obtener URL directa del video
    const res = await fetch(`/video_url?url=${encodeURIComponent(urlVideo)}`);
    if (!res.ok) throw new Error("No se pudo obtener la URL del video");
    const { direct_url } = await res.json();

    // Preparar URL para el player
    const proxyUrl = `/video-player?url=${encodeURIComponent(direct_url)}`;

    if (Hls.isSupported()) {
      const hls = new Hls();
      hls.loadSource(proxyUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play());
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = proxyUrl;
      video.addEventListener("loadedmetadata", () => video.play());
    } else {
      throw new Error("HLS no soportado");
    }

    // Ocultar loader y mostrar video
    loader.style.display = 'none';
    video.style.display = 'block';
    modalLocked = false;

  } catch (e) {
    console.error(e);
    alert("No se pudo reproducir el video");
    // Cerrar modal en caso de error
    video.pause();
    video.src = "";
    modal.classList.remove('show');
    modalLocked = false;
  }
}


function closeVideoModal() {
  const modal = document.getElementById('modal-video');
  const video = document.getElementById('video-player');
  const loader = document.getElementById('video-loader');

  video.pause();
  video.src = "";
  video.style.display = 'none';
  loader.style.display = 'none';
  modal.classList.remove('show');
}

// Cerrar modales al hacer click fuera (si no está bloqueado)
window.onclick = function (event) {
  const download = document.getElementById("modal-download");
  const video = document.getElementById("modal-video");

  if (event.target === download && !modalLocked) closeModal();
  if (event.target === video && !modalLocked) closeVideoModal();
};
