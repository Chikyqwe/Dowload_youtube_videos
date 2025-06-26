    // Variables para modales
    let currentUrl = "";
    let downloadModal = null;
    let videoModal = null;

    // Abre modal descarga con URL
    function openModal(url) {
      currentUrl = url;
      downloadModal = document.getElementById("modal-download");
      downloadModal.classList.add("show");
      resetProgress();

      // Configurar botón iniciar descarga
      const btn = document.getElementById("start-download");
      btn.disabled = false;
      btn.textContent = "Iniciar descarga";
      btn.onclick = () => iniciarDescarga(currentUrl);
    }

    // Cierra modal descarga
    function closeModal() {
      if (downloadModal) {
        downloadModal.classList.remove("show");
        resetProgress();
      }
    }

    // Resetea barra de progreso
    function resetProgress() {
      const progress = document.getElementById("progress");
      progress.style.width = "0%";
    }

    async function iniciarDescarga(url) {
  const formato = document.getElementById("formato").value;
  const btn = document.getElementById("start-download");
  const progress = document.getElementById("progress");

  btn.disabled = true;
  btn.textContent = "Iniciando descarga...";

  // 1. Solicitar inicio de descarga y recibir id
  const res = await fetch(`/download?url=${encodeURIComponent(url)}&format=${formato}`);
  const data = await res.json();
  if (!data.download_id) {
    alert("Error iniciando la descarga");
    btn.disabled = false;
    btn.textContent = "Iniciar descarga";
    return;
  }

  const downloadId = data.download_id;
  progress.style.width = "0%";

  // 2. Polling cada segundo para actualizar barra
  const intervalo = setInterval(async () => {
    const resp = await fetch(`/progress?id=${downloadId}`);
    const progresoData = await resp.json();

    if (progresoData.progress >= 0) {
      progress.style.width = progresoData.progress + "%";
    }

if (progresoData.progress === 100) {
  clearInterval(intervalo);

  setTimeout(async () => {
    let intentos = 0;
    const maxIntentos = 12;
    let exito = false;

    while (intentos < maxIntentos && !exito) {
      try {
        const response = await fetch(`/get_file?id=${downloadId}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const disposition = response.headers.get('Content-Disposition');
        let filename = 'archivo.mp3'; // fallback
        if (disposition && disposition.indexOf('filename=') !== -1) {
          const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
          const matches = filenameRegex.exec(disposition);
          if (matches != null && matches[1]) {
            filename = matches[1].replace(/['"]/g, '');
          }
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;  // <-- Aquí asignas el nombre real extraído
        a.style.display = 'none';

        document.body.appendChild(a);
        a.click();
        a.remove();

        window.URL.revokeObjectURL(url);
        exito = true;
        btn.textContent = "Espere porfavor...";
        
setTimeout(() => {
  btn.disabled = false;
  btn.textContent = "Iniciar descarga";
  closeModal();
}, 2000); // 2000 milisegundos = 2 segundos

      } catch (error) {
        console.warn(`Intento ${intentos + 1} fallido:`, error);
        intentos++;
        await new Promise(resolve => setTimeout(resolve, 5000));  // Espera 1 segundo antes del siguiente intento
      }
    }

    if (!exito) {
      btn.textContent = "Error en la descarga";
      btn.disabled = false;
      alert("No se pudo descargar el archivo tras varios intentos.");
    }
  }, 3000);
}

    if (progresoData.progress === -1) {
      clearInterval(intervalo);
      alert("Error en la descarga");
      btn.disabled = false;
      btn.textContent = "Iniciar descarga";
    }
  }, 1000);
}

// Función para obtener URL real y abrir modal
async function reproducirVideo(urlVideo) {
  try {
    openVideoModal()
    const res = await fetch(`/video_url?url=${encodeURIComponent(urlVideo)}`);
    if (!res.ok) throw new Error("Error al obtener URL del video");
    const data = await res.json();
    openVideoModal(data.direct_url);
  } catch (error) {
    alert("No se pudo cargar el video");
    console.error(error);
  }
}


    // Abre modal video para reproducir mp4
    function openVideoModal(url) {
      videoModal = document.getElementById("modal-video");
      videoModal.classList.add("show");

      const videoEl = document.getElementById("video-player");
      videoEl.src = url;
      videoEl.load();
      videoEl.play();
    }

    // Cierra modal video
    function closeVideoModal() {
      if (!videoModal) return;
      const videoEl = document.getElementById("video-player");
      videoEl.pause();
      videoEl.src = "";
      videoModal.classList.remove("show");
    }

    // Cerrar modal con click fuera contenido
    window.onclick = function(event) {
      if (event.target === downloadModal) closeModal();
      if (event.target === videoModal) closeVideoModal();
    }

    // Función búsqueda simulada, remplaza con backend real
    async function buscar() {
    const q = document.getElementById("query").value.trim();
    if (!q) return alert("Por favor, escribe algo para buscar.");

    try {
      const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error("Error en la respuesta del servidor");

      const videos = await res.json();
      const container = document.getElementById("resultados");
      container.innerHTML = "";

      if (!videos.length) {
        container.innerHTML = `<p>No se encontraron resultados.</p>`;
        return;
      }

      videos.forEach(v => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <div class="media-container">
            <img src="${v.thumbnail}" alt="Miniatura video" loading="lazy" />
          </div>
          <h3>${v.title}</h3>
          <div class="buttons-container">
            <button class="btn-download" onclick="openModal('${v.url}')">Descargar</button>
            <button class="btn-play" onclick="reproducirVideo('${v.url}')">Reproducir</button>

          </div>
        `;
        container.appendChild(card);
      });

    } catch (e) {
      alert("Error al buscar videos. Intenta de nuevo más tarde.");
      console.error(e);
    }
  }