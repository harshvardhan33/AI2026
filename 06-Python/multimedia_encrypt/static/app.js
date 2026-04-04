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
  // Collect all chunk ArrayBuffers, combine into a single Blob, render as <img>
  const buffers = [];

  for (let i = 0; i < file.total_chunks; i++) {
    if (!holdActive) return; // user released during fetch

    const buf = await fetchChunk(token, file.file_id, i);
    if (buf === null) return; // error or token expired

    buffers.push(buf);
  }

  if (!holdActive) return;

  // Combine all chunk buffers into a single image Blob
  const blob = new Blob(buffers, { type: file.mime_type });
  const url  = URL.createObjectURL(blob);

  const img = document.createElement("img");
  img.alt   = `Revealed: ${file.original_filename}`;
  img.src   = url;
  // Revoke the object URL once the browser has read it into its image cache
  img.onload  = () => URL.revokeObjectURL(url);
  img.onerror = () => URL.revokeObjectURL(url);

  revealContainer.innerHTML = "";
  revealContainer.appendChild(img);
}

async function streamText(token, file) {
  // Decode each chunk progressively and append to a <pre> element.
  // TextDecoder with { stream: true } handles multi-byte chars split across chunks.
  const decoder = new TextDecoder("utf-8");
  const pre = document.createElement("pre");
  revealContainer.innerHTML = "";
  revealContainer.appendChild(pre);

  for (let i = 0; i < file.total_chunks; i++) {
    if (!holdActive) return;

    const buf = await fetchChunk(token, file.file_id, i);
    if (buf === null) return;

    const isLast = i === file.total_chunks - 1;
    pre.textContent += decoder.decode(buf, { stream: !isLast });
  }
}

async function streamAudio(token, file) {
  // Collect all chunks, combine into a Blob, render as <audio>
  const buffers = [];
  for (let i = 0; i < file.total_chunks; i++) {
    if (!holdActive) return;
    const buf = await fetchChunk(token, file.file_id, i);
    if (buf === null) return;
    buffers.push(buf);
  }
  if (!holdActive) return;

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
  // Collect all chunks, combine into a Blob, render as <video>
  const buffers = [];
  for (let i = 0; i < file.total_chunks; i++) {
    if (!holdActive) return;
    const buf = await fetchChunk(token, file.file_id, i);
    if (buf === null) return;
    buffers.push(buf);
  }
  if (!holdActive) return;

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
// Init
// ══════════════════════════════════════════════════════════════════════════════

loadFileList();
