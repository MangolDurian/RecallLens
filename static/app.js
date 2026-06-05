const state = {
  apiBase: defaultApiBase(),
  latitude: null,
  longitude: null,
  images: [],
};

const els = {
  apiForm: document.querySelector("#api-form"),
  apiBase: document.querySelector("#api-base"),
  status: document.querySelector("#status"),
  tabs: document.querySelectorAll(".tab"),
  views: document.querySelectorAll(".view"),
  searchForm: document.querySelector("#search-form"),
  voiceButton: document.querySelector("#voice-button"),
  uploadForm: document.querySelector("#upload-form"),
  gpsButton: document.querySelector("#gps-button"),
  fileInput: document.querySelector("#image"),
  fileLabel: document.querySelector("#file-label"),
  results: document.querySelector("#results"),
  library: document.querySelector("#library"),
  tags: document.querySelector("#tags"),
  queries: document.querySelector("#queries"),
  detail: document.querySelector("#detail"),
};

els.apiBase.value = state.apiBase;

els.apiForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.apiBase = normalizeBase(els.apiBase.value);
  localStorage.setItem("recalllens.apiBase", state.apiBase);
  connect();
});

els.tabs.forEach((tab) => {
  tab.addEventListener("click", () => showView(tab.dataset.view));
});

els.fileInput.addEventListener("change", () => {
  const file = els.fileInput.files[0];
  els.fileLabel.textContent = file ? file.name : "Choose or take a photo";
});

els.gpsButton.addEventListener("click", () => {
  if (!navigator.geolocation) {
    setStatus("Geolocation is unavailable in this browser.", true);
    return;
  }
  els.gpsButton.textContent = "Locating...";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      state.latitude = position.coords.latitude;
      state.longitude = position.coords.longitude;
      els.gpsButton.textContent = "GPS saved";
    },
    (error) => {
      els.gpsButton.textContent = "Use GPS";
      setStatus(error.message, true);
    },
    { enableHighAccuracy: true, timeout: 10000 },
  );
});

els.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = els.fileInput.files[0];
  if (!file) {
    setStatus("Choose a photo first.", true);
    return;
  }

  try {
    setStatus("Indexing photo...");
    const body = {
      imageBase64: await fileToDataUrl(file),
      originalFilename: file.name,
      note: value("#note") || null,
      capturedAt: value("#captured-at") || null,
      latitude: state.latitude,
      longitude: state.longitude,
      locationLabel: value("#location-label") || null,
    };
    const record = await request("/api/images", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    els.uploadForm.reset();
    els.fileLabel.textContent = "Choose or take a photo";
    state.latitude = null;
    state.longitude = null;
    els.gpsButton.textContent = "Use GPS";
    setStatus("Photo indexed.");
    await refreshLibrary();
    await refreshTags();
    showDetail(record);
  } catch (error) {
    setStatus(error.message, true);
  }
});

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const queryText = value("#query");
  if (!queryText) {
    setStatus("Enter a search query.", true);
    return;
  }
  try {
    setStatus("Searching...");
    const response = await request("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        queryText,
        limit: Number(value("#limit") || 5),
        capturedFrom: value("#captured-from") || null,
        capturedTo: value("#captured-to") || null,
        locationText: value("#location-filter") || null,
      }),
    });
    renderCards(els.results, response.results, true);
    setStatus(response.results.length ? `Found ${response.results.length} result(s).` : "No matches.");
    await refreshQueries();
  } catch (error) {
    setStatus(error.message, true);
  }
});

els.voiceButton.addEventListener("click", () => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("Voice input is unavailable in this browser.", true);
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    els.voiceButton.textContent = "Listening...";
    els.voiceButton.disabled = true;
  };
  recognition.onend = () => {
    els.voiceButton.textContent = "Voice";
    els.voiceButton.disabled = false;
  };
  recognition.onerror = () => {
    setStatus("Voice input stopped.", true);
  };
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript;
    if (transcript) {
      document.querySelector("#query").value = transcript;
    }
  };
  recognition.start();
});

connect();
registerServiceWorker();

function defaultApiBase() {
  const saved = localStorage.getItem("recalllens.apiBase");
  if (saved) {
    return saved;
  }
  if (location.protocol === "http:" || location.protocol === "https:") {
    return location.origin;
  }
  return "http://localhost:8000";
}

async function connect() {
  try {
    setStatus("Connecting...");
    const health = await request("/api/health");
    setStatus(`${health.indexedImages} indexed · ${health.embedder} · ${health.vectorBackend}`);
    await refreshLibrary();
    await refreshTags();
    await refreshQueries();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function refreshLibrary() {
  state.images = await request("/api/images");
  renderCards(els.library, state.images, false);
}

async function refreshQueries() {
  const queries = await request("/api/queries?limit=20");
  renderQueries(queries);
}

async function refreshTags() {
  const tags = await request("/api/tags");
  renderTags(tags);
}

async function request(path, options = {}) {
  const response = await fetch(`${state.apiBase}${path}`, options);
  const text = await response.text();
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    if (text) {
      try {
        message = JSON.parse(text).detail || message;
      } catch {
        message = text;
      }
    }
    throw new Error(message);
  }
  return text ? JSON.parse(text) : null;
}

function renderCards(container, items, includeScore) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = '<p class="status">No photos yet.</p>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "card";
    card.innerHTML = `
      <img src="${escapeAttr(mediaUrl(item.thumbnailUrl))}" alt="${escapeAttr(item.originalFilename)}" />
      <span class="card-body">
        <strong>${escapeHtml(item.userNotes || item.originalFilename)}</strong>
        <span>${escapeHtml(formatDate(item.capturedAt || item.uploadTime))}</span>
        <span>${escapeHtml(formatLocation(item.location))}</span>
        ${includeScore ? `<span class="score">${Math.round((item.score || 0) * 100)}%</span>` : ""}
      </span>
    `;
    card.addEventListener("click", () => showDetail(item));
    container.appendChild(card);
  });
}

function renderQueries(queries) {
  els.queries.innerHTML = "";
  if (!queries.length) {
    els.queries.innerHTML = '<p class="status">No searches yet.</p>';
    return;
  }
  queries.forEach((query) => {
    const item = document.createElement("article");
    item.className = "query-item";
    const filters = [
      query.capturedFrom ? `from ${query.capturedFrom}` : "",
      query.capturedTo ? `to ${query.capturedTo}` : "",
      query.locationText ? `place ${query.locationText}` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    item.innerHTML = `
      <strong>${escapeHtml(query.queryText)}</strong>
      <span>${escapeHtml(formatDate(query.createdAt))}</span>
      <span>${escapeHtml(query.results.length ? `results: ${query.results.join(", ")}` : "no results")}</span>
      <span>${escapeHtml(filters || "no explicit filters")}</span>
    `;
    els.queries.appendChild(item);
  });
}

function renderTags(tags) {
  els.tags.innerHTML = "";
  if (!tags.length) {
    els.tags.innerHTML = '<p class="status">No semantic tags yet.</p>';
    return;
  }
  tags.forEach((tag) => {
    const item = document.createElement("article");
    item.className = "tag-item";
    item.innerHTML = `
      <strong>${escapeHtml(tag.tag)}</strong>
      <span>${tag.count} photo${tag.count === 1 ? "" : "s"}</span>
      <span>${escapeHtml(tag.imageIds.join(", "))}</span>
    `;
    els.tags.appendChild(item);
  });
}

function showDetail(item) {
  els.detail.className = "detail";
  els.detail.innerHTML = `
    <img src="${escapeAttr(mediaUrl(item.imageUrl))}" alt="${escapeAttr(item.originalFilename)}" />
    <dl>
      <dt>File</dt><dd>${escapeHtml(item.originalFilename)}</dd>
      <dt>Notes</dt><dd>${escapeHtml(item.userNotes || "No notes")}</dd>
      <dt>Tags</dt><dd>${escapeHtml(formatDescription(item.description))}</dd>
      <dt>Embedding</dt><dd>${escapeHtml(formatEmbedding(item))}</dd>
      <dt>Time</dt><dd>${escapeHtml(formatDate(item.capturedAt || item.uploadTime))}</dd>
      <dt>Place</dt><dd>${escapeHtml(formatLocation(item.location))}</dd>
      <dt>Status</dt><dd>${escapeHtml(item.indexStatus)}</dd>
    </dl>
  `;
}

function showView(view) {
  els.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  els.views.forEach((panel) => panel.classList.toggle("active", panel.id === `${view}-view`));
}

function mediaUrl(path) {
  if (!path || path.startsWith("http")) {
    return path;
  }
  return `${state.apiBase}${path}`;
}

function normalizeBase(value) {
  return (value || "http://localhost:8000").replace(/\/$/, "");
}

function value(selector) {
  return document.querySelector(selector).value.trim();
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(reader.error || new Error("Cannot read file.")));
    reader.readAsDataURL(file);
  });
}

function setStatus(message, isError = false) {
  els.status.textContent = message;
  els.status.classList.toggle("error", isError);
}

function formatDate(rawValue) {
  if (!rawValue) {
    return "No time";
  }
  const date = new Date(rawValue);
  if (Number.isNaN(date.getTime())) {
    return rawValue;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatLocation(location) {
  if (!location) {
    return "No location";
  }
  if (location.label) {
    return location.label;
  }
  if (location.latitude !== null && location.longitude !== null) {
    return `${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`;
  }
  return "No location";
}

function formatDescription(description) {
  return (description || "No tags").replace(/^Semantic tags:\s*/i, "").replace(/\.$/, "");
}

function formatEmbedding(item) {
  if (!item.embeddingModel && item.embeddingDimension === null) {
    return "No embedding metadata";
  }
  return [item.embeddingModel, item.embeddingDimension !== null ? `${item.embeddingDimension}d` : null, item.embeddingNorm !== null ? `norm ${item.embeddingNorm}` : null]
    .filter(Boolean)
    .join(" · ");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return entities[char];
  });
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => undefined);
  });
}
