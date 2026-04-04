"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────
const API = "/api";

// ── State ──────────────────────────────────────────────────────────────────────
let currentFile = null;   // { file_id, original_filename, mime_type, total_chunks }
let revealToken = null;
let holdActive  = false;
let tokenRefreshTimer = null;
let ttlBarTimer = null;
let ttlSeconds = 30;

// ── DOM refs ───────────────────────────────────────────────────────────────────
const uploadForm      = document.getElementById("upload-form");
const fileInput       = document.getElementById("file-input");
const uploadStatus    = document.getElementById("upload-status");
const fileList        = document.getElementById("file-list");
const revealSection   = document.getElementById("reveal-section");
const revealFilename  = document.getElementById("reveal-filename");
const holdBtn         = document.getElementById("hold-btn");
const revealContainer = document.getElementById("reveal-container");
const closeRevealBtn  = document.getElementById("close-reveal-btn");
const ttlBar          = document.getElementById("ttl-bar");

// Analysis modal
const analysisModal        = document.getElementById("analysis-modal");
const analysisBackdrop     = document.getElementById("analysis-backdrop");
const analysisModalTitle   = document.getElementById("analysis-modal-title");
const analysisModalFilename= document.getElementById("analysis-modal-filename");
const analysisPanelBody    = document.getElementById("analysis-panel-body");
const analysisCloseBtn     = document.getElementById("analysis-close-btn");

let analysisPollTimer   = null;
let analysisCurrentFile = null;


// ══════════════════════════════════════════════════════════════════════════════
// Upload
// ══════════════════════════════════════════════════════════════════════════════

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  setStatus("Encrypting and uploading…", false);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`${API}/upload`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      setStatus(`Error ${res.status}: ${err.detail}`, true);
      return;
    }
    const data = await res.json();
    setStatus(`Stored with ID ${data.file_id.slice(0, 8)}…`, false);
    fileInput.value = "";
    await loadFileList();
  } catch (err) {
    setStatus(`Network error: ${err.message}`, true);
  }
});

function setStatus(msg, isError) {
  uploadStatus.textContent = msg;
  uploadStatus.className = isError ? "error" : "";
}


// ══════════════════════════════════════════════════════════════════════════════
// File listing
// ══════════════════════════════════════════════════════════════════════════════

document.getElementById("refresh-btn").addEventListener("click", loadFileList);

async function loadFileList() {
  try {
    const res = await fetch(`${API}/files`);
    const data = await res.json();
    renderFileList(data.files || []);
  } catch (err) {
    fileList.innerHTML = `<li class="empty-msg">Failed to load files: ${escHtml(err.message)}</li>`;
  }
}

function renderFileList(files) {
  if (files.length === 0) {
    fileList.innerHTML = `<li class="empty-msg">No files stored yet. Upload one above.</li>`;
    return;
  }
  fileList.innerHTML = "";
  for (const f of files) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="ftype-badge">${escHtml(f.media_type)}</span>
      <span class="fname" title="${escHtml(f.original_filename)}">${escHtml(f.original_filename)}</span>
      <span class="fmeta">${formatBytes(f.total_bytes)} · ${f.total_chunks} chunk${f.total_chunks !== 1 ? "s" : ""}</span>
      <button
        class="btn-reveal"
        data-id="${escHtml(f.file_id)}"
        data-name="${escHtml(f.original_filename)}"
        data-mime="${escHtml(f.mime_type)}"
        data-chunks="${f.total_chunks}"
        aria-label="Select ${escHtml(f.original_filename)} for reveal"
      >Select</button>
      <button
        class="btn-delete"
        data-id="${escHtml(f.file_id)}"
        aria-label="Delete ${escHtml(f.original_filename)}"
      >Delete</button>
      <button
        class="btn-analysis"
        data-id="${escHtml(f.file_id)}"
        data-name="${escHtml(f.original_filename)}"
        aria-label="AI analysis for ${escHtml(f.original_filename)}"
      >Analysis</button>
    `;
    fileList.appendChild(li);
  }
}

fileList.addEventListener("click", async (e) => {
  if (e.target.closest(".btn-reveal")) {
    const btn = e.target.closest(".btn-reveal");
    selectFile({
      file_id:           btn.dataset.id,
      original_filename: btn.dataset.name,
      mime_type:         btn.dataset.mime,
      total_chunks:      parseInt(btn.dataset.chunks, 10),
    });
    return;
  }

  if (e.target.closest(".btn-analysis")) {
    const btn = e.target.closest(".btn-analysis");
    openAnalysisModal(btn.dataset.id, btn.dataset.name);
    return;
  }

  if (e.target.closest(".btn-delete")) {
    const btn = e.target.closest(".btn-delete");
    const fileId = btn.dataset.id;
    try {
      const res = await fetch(`${API}/files/${fileId}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        alert(`Delete failed: ${err.detail}`);
        return;
      }
      // If the deleted file is currently selected, close the reveal section
      if (currentFile && currentFile.file_id === fileId) {
        if (holdActive) stopReveal();
        wipeContent();
        revealSection.hidden = true;
        currentFile = null;
      }
      // Close analysis modal if it's showing this file
      if (analysisCurrentFile === fileId) closeAnalysisModal();
      await loadFileList();
    } catch (err) {
      alert(`Network error: ${err.message}`);
    }
  }
});


// ══════════════════════════════════════════════════════════════════════════════
// File selection
// ══════════════════════════════════════════════════════════════════════════════

function selectFile(file) {
  // Wipe any previous reveal first
  if (holdActive) stopReveal();
  wipeContent();

  currentFile = file;
  revealFilename.textContent = file.original_filename;
  revealSection.hidden = false;
  revealSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

closeRevealBtn.addEventListener("click", () => {
  if (holdActive) stopReveal();
  wipeContent();
  revealSection.hidden = true;
  currentFile = null;
});


// ══════════════════════════════════════════════════════════════════════════════
// Hold-to-reveal core mechanic
// ══════════════════════════════════════════════════════════════════════════════

// Mouse events
holdBtn.addEventListener("mousedown",  startReveal);
holdBtn.addEventListener("mouseup",    stopReveal);
holdBtn.addEventListener("mouseleave", stopReveal);

// Touch events (prevent default to block scroll/zoom during hold)
holdBtn.addEventListener("touchstart", (e) => { e.preventDefault(); startReveal(); }, { passive: false });
holdBtn.addEventListener("touchend",   (e) => { e.preventDefault(); stopReveal();  }, { passive: false });
holdBtn.addEventListener("touchcancel",(e) => { e.preventDefault(); stopReveal();  }, { passive: false });


async function startReveal() {
  if (holdActive || !currentFile) return;
  holdActive = true;
  holdBtn.classList.add("active");

  // Clear previous content and remove blur
  wipeContent();
  revealContainer.classList.remove("blurred");

  try {
    // 1. Mint a session token from the server
    const res = await fetch(`${API}/reveal/start/${currentFile.file_id}`, {
      method: "POST",
    });
    if (!res.ok) {
      console.error("reveal/start failed:", res.status);
      stopReveal();
      return;
    }
    const { token, ttl } = await res.json();
    revealToken = token;
    ttlSeconds = ttl;

    // Start TTL progress bar animation
    startTtlBar(ttl);

    // Schedule token refresh at 80% of TTL (before it expires mid-stream)
    tokenRefreshTimer = setTimeout(refreshToken, ttl * 800);

    // 2. Stream and render all chunks
    await streamChunks(token, currentFile);
  } catch (err) {
    console.error("Reveal error:", err);
    stopReveal();
  }
}

async function stopReveal() {
  if (!holdActive) return;
  holdActive = false;
  holdBtn.classList.remove("active");

  // Cancel scheduled token refresh
  if (tokenRefreshTimer) {
    clearTimeout(tokenRefreshTimer);
    tokenRefreshTimer = null;
  }
  stopTtlBar();

  // Revoke server-side token (fire-and-forget; idempotent endpoint)
  if (revealToken) {
    const t = revealToken;
    revealToken = null;
    fetch(`${API}/reveal/end/${t}`, { method: "DELETE" }).catch(() => {});
  }

  // Wipe all decrypted content from DOM
  wipeContent();
}

async function refreshToken() {
  if (!holdActive || !currentFile) return;

  // Revoke old token and mint a fresh one, keeping reveal alive
  if (revealToken) {
    const old = revealToken;
    revealToken = null;
    fetch(`${API}/reveal/end/${old}`, { method: "DELETE" }).catch(() => {});
  }

  try {
    const res = await fetch(`${API}/reveal/start/${currentFile.file_id}`, {
      method: "POST",
    });
    if (!res.ok) { stopReveal(); return; }
    const { token, ttl } = await res.json();
    revealToken = token;

    // Reset TTL bar and schedule next refresh
    startTtlBar(ttl);
    tokenRefreshTimer = setTimeout(refreshToken, ttl * 800);
  } catch (err) {
    console.error("Token refresh failed:", err);
  }
}


// ══════════════════════════════════════════════════════════════════════════════
// Chunk streaming and rendering
// ══════════════════════════════════════════════════════════════════════════════

async function streamChunks(token, file) {
  if (file.mime_type.startsWith("image/")) {
    await streamImage(token, file);
  } else if (file.mime_type.startsWith("audio/")) {
    await streamAudio(token, file);
  } else if (file.mime_type.startsWith("video/")) {
    await streamVideo(token, file);
  } else {
    await streamText(token, file);
  }
}

async function streamImage(token, file) {
  // Fetch all chunks in parallel, then combine into a single Blob
  const buffers = await fetchAllChunks(token, file);
  if (!buffers) return;

  const blob = new Blob(buffers, { type: file.mime_type });
  const url  = URL.createObjectURL(blob);

  const img   = document.createElement("img");
  img.alt     = `Revealed: ${file.original_filename}`;
  img.src     = url;
  img.onload  = () => URL.revokeObjectURL(url);
  img.onerror = () => URL.revokeObjectURL(url);

  revealContainer.innerHTML = "";
  revealContainer.appendChild(img);
}

async function streamText(token, file) {
  // Fetch all chunks in parallel, then decode in order
  const buffers = await fetchAllChunks(token, file);
  if (!buffers) return;

  const decoder = new TextDecoder("utf-8");
  const pre     = document.createElement("pre");
  revealContainer.innerHTML = "";
  revealContainer.appendChild(pre);

  for (let i = 0; i < buffers.length; i++) {
    const isLast = i === buffers.length - 1;
    pre.textContent += decoder.decode(buffers[i], { stream: !isLast });
  }
}

async function streamAudio(token, file) {
  // Fetch all chunks in parallel, then combine into a Blob
  const buffers = await fetchAllChunks(token, file);
  if (!buffers) return;

  const blob = new Blob(buffers, { type: file.mime_type });
  const url  = URL.createObjectURL(blob);

  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = url;
  audio.onended  = () => URL.revokeObjectURL(url);
  audio.onerror  = () => URL.revokeObjectURL(url);

  revealContainer.innerHTML = "";
  revealContainer.appendChild(audio);
  audio.play().catch(() => {});
}

async function streamVideo(token, file) {
  // Fetch all chunks in parallel, then combine into a Blob
  const buffers = await fetchAllChunks(token, file);
  if (!buffers) return;

  const blob = new Blob(buffers, { type: file.mime_type });
  const url  = URL.createObjectURL(blob);

  const video = document.createElement("video");
  video.controls = true;
  video.src = url;
  video.onended  = () => URL.revokeObjectURL(url);
  video.onerror  = () => URL.revokeObjectURL(url);

  revealContainer.innerHTML = "";
  revealContainer.appendChild(video);
  video.play().catch(() => {});
}

async function fetchAllChunks(token, file) {
  /**
   * Fire all chunk requests in parallel (Promise.all).
   * Returns an ordered array of ArrayBuffers, or null if any chunk failed
   * or the user released hold mid-flight.
   */
  if (!holdActive) return null;

  const promises = Array.from({ length: file.total_chunks }, (_, i) =>
    fetchChunk(token, file.file_id, i)
  );

  const buffers = await Promise.all(promises);
  if (!holdActive) return null;

  const failedIdx = buffers.findIndex(b => b === null);
  if (failedIdx !== -1) {
    console.warn(`Chunk ${failedIdx} failed to load`);
    return null;
  }

  return buffers;
}

async function fetchChunk(token, fileId, index) {
  try {
    const res = await fetch(`${API}/reveal/chunk/${token}/${fileId}/${index}`);
    if (!res.ok) {
      console.warn(`Chunk ${index} fetch failed: ${res.status}`);
      return null;
    }
    return await res.arrayBuffer();
  } catch (err) {
    console.warn(`Chunk ${index} network error:`, err);
    return null;
  }
}


// ══════════════════════════════════════════════════════════════════════════════
// DOM wipe
// ══════════════════════════════════════════════════════════════════════════════

function wipeContent() {
  // innerHTML = "" detaches all child nodes synchronously.
  // Any <img> object URLs are revoked in their onload handlers.
  revealContainer.innerHTML =
    '<p class="reveal-placeholder">Hold the button above to reveal content</p>';
  revealContainer.classList.add("blurred");
}


// ══════════════════════════════════════════════════════════════════════════════
// TTL progress bar
// ══════════════════════════════════════════════════════════════════════════════

function startTtlBar(ttl) {
  stopTtlBar();
  ttlBar.style.transition = "none";
  ttlBar.style.width = "100%";
  // Force reflow so transition resets visually
  void ttlBar.offsetWidth;
  ttlBar.style.transition = `width ${ttl}s linear`;
  ttlBar.style.width = "0%";
}

function stopTtlBar() {
  if (ttlBarTimer) { clearTimeout(ttlBarTimer); ttlBarTimer = null; }
  ttlBar.style.transition = "none";
  ttlBar.style.width = "0%";
}


// ══════════════════════════════════════════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════════════════════════════════════════

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatBytes(n) {
  if (n < 1024)      return `${n} B`;
  if (n < 1048576)   return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}


// ══════════════════════════════════════════════════════════════════════════════
// Analysis modal
// ══════════════════════════════════════════════════════════════════════════════

analysisCloseBtn.addEventListener("click", closeAnalysisModal);
analysisBackdrop.addEventListener("click", closeAnalysisModal);

function openAnalysisModal(fileId, filename) {
  analysisCurrentFile = fileId;
  analysisModalFilename.textContent = filename;
  analysisPanelBody.innerHTML = '<p class="analysis-pending">Analysing… this may take a minute on first run (models are downloading).</p>';
  analysisModal.hidden = false;
  fetchAnalysis(fileId);
}

function closeAnalysisModal() {
  if (analysisPollTimer) { clearTimeout(analysisPollTimer); analysisPollTimer = null; }
  analysisModal.hidden = true;
  analysisCurrentFile = null;
}

async function fetchAnalysis(fileId) {
  if (analysisCurrentFile !== fileId) return;

  let data;
  try {
    const res = await fetch(`${API}/files/${fileId}/analysis`);
    if (res.status === 404) { closeAnalysisModal(); return; }
    data = await res.json();
  } catch (err) {
    analysisPanelBody.innerHTML = `<p class="analysis-error">Network error: ${escHtml(err.message)}</p>`;
    return;
  }

  if (data.status === "pending") {
    analysisPanelBody.innerHTML = '<p class="analysis-pending">Analysing… check back in a moment.</p>';
    analysisPollTimer = setTimeout(() => fetchAnalysis(fileId), 3000);
    return;
  }

  if (data.status === "failed") {
    analysisPanelBody.innerHTML = `<p class="analysis-error">Analysis failed: ${escHtml(data.error || "unknown error")}</p>`;
    return;
  }

  renderAnalysisResult(data);
}

function renderAnalysisResult(data) {
  const sections = [];

  if (data.error) {
    sections.push(`<p class="analysis-error">Error: ${escHtml(data.error)}</p>`);
  }

  // ── Text ──
  if (data.type === "text") {
    sections.push(aInfoRow("Words", data.word_count));
    sections.push(aInfoRow("Characters", data.char_count));
    if (data.summary) {
      sections.push(aSection("Summary", `<p class="analysis-summary">${escHtml(data.summary)}</p>`));
    }
    if (data.entities && Object.keys(data.entities).length > 0) {
      const rows = Object.entries(data.entities).map(([label, items]) =>
        `<div class="entity-row">
          <span class="entity-label">${escHtml(label)}</span>
          <span class="entity-vals">${items.map(escHtml).join(", ")}</span>
         </div>`
      ).join("");
      sections.push(aSection("Named Entities", rows));
    }
  }

  // ── Audio ──
  if (data.type === "audio") {
    renderAudioFields(data, sections);
  }

  // ── Image ──
  if (data.type === "image") {
    if (data.image_size) sections.push(aInfoRow("Dimensions", `${data.image_size[0]} × ${data.image_size[1]} px`));
    if (data.caption)    sections.push(aSection("AI Description", `<p class="analysis-caption">${escHtml(data.caption)}</p>`));
    renderDetections(data.detections, sections);
    if (data.ocr_text)   sections.push(aSection("OCR Text", `<pre>${escHtml(data.ocr_text)}</pre>`));
  }

  // ── Video ──
  if (data.type === "video") {
    sections.push(aInfoRow("Duration", `${data.duration_seconds}s`));
    sections.push(aInfoRow("Frames analysed", data.frames_analyzed));
    if (data.scene_captions && data.scene_captions.length > 0) {
      const items = data.scene_captions.map((c, i) =>
        `<div class="scene-caption"><span class="scene-num">Scene ${i + 1}</span>${escHtml(c)}</div>`
      ).join("");
      sections.push(aSection("Scene Descriptions (AI)", `<div class="scene-list">${items}</div>`));
    }
    renderDetections(data.detections, sections);
    if (data.ocr_text) sections.push(aSection("OCR Text", `<pre>${escHtml(data.ocr_text)}</pre>`));
    if (data.audio) {
      sections.push(aSection("Audio Track", buildAudioHtml(data.audio)));
    }
  }

  if (sections.length === 0) {
    analysisPanelBody.innerHTML = '<p class="analysis-empty">No analysis data available.</p>';
    return;
  }
  analysisPanelBody.innerHTML = sections.join("");
}

function renderAudioFields(a, sections) {
  if (a.language) sections.push(aInfoRow("Language", a.language));
  if (a.sentiment) {
    const cls = a.sentiment.label === "positive" ? "sent-pos"
              : a.sentiment.label === "negative" ? "sent-neg"
              : "sent-neu";
    sections.push(aInfoRow("Sentiment",
      `<span class="sentiment-badge ${cls}">${escHtml(a.sentiment.label)}</span> `
      + `<span class="sent-score">${(a.sentiment.score * 100).toFixed(1)}%</span>`
    ));
  }
  if (a.transcript) sections.push(aSection("Transcript", `<pre>${escHtml(a.transcript)}</pre>`));
  if (a.error)      sections.push(`<p class="analysis-error">${escHtml(a.error)}</p>`);
}

function buildAudioHtml(a) {
  const parts = [];
  if (a.language)   parts.push(`<p><strong>Language:</strong> ${escHtml(a.language)}</p>`);
  if (a.sentiment)  parts.push(`<p><strong>Sentiment:</strong> ${escHtml(a.sentiment.label)} (${(a.sentiment.score * 100).toFixed(1)}%)</p>`);
  if (a.transcript) parts.push(`<pre>${escHtml(a.transcript)}</pre>`);
  if (a.error)      parts.push(`<p class="analysis-error">${escHtml(a.error)}</p>`);
  return parts.join("") || "<p>No audio data.</p>";
}

function renderDetections(detections, sections) {
  if (!detections || detections.length === 0) return;
  const tags = detections.map(d =>
    `<span class="det-tag">${escHtml(d.object)} <span class="det-conf">${(d.confidence * 100).toFixed(0)}%</span></span>`
  ).join("");
  sections.push(aSection("Detected Objects", `<div class="det-tags">${tags}</div>`));
}

function aSection(title, bodyHtml) {
  return `<div class="analysis-sect">
    <div class="analysis-sect-title">${escHtml(title)}</div>
    <div class="analysis-sect-body">${bodyHtml}</div>
  </div>`;
}

function aInfoRow(label, value) {
  return `<div class="analysis-info-row">
    <span class="analysis-info-label">${escHtml(label)}</span>
    <span class="analysis-info-val">${escHtml(String(value))}</span>
  </div>`;
}


// ══════════════════════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════════════════════

loadFileList();
