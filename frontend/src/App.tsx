import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Camera,
  Clock3,
  ExternalLink,
  Image as ImageIcon,
  ImagePlus,
  Images,
  Loader2,
  LocateFixed,
  MapPin,
  Mic,
  RefreshCw,
  Search,
  SlidersHorizontal,
  UploadCloud,
  X,
} from "lucide-react";
import {
  getHealth,
  listImages,
  mediaUrl,
  searchImages,
  uploadImage,
} from "./api";
import type { HealthResponse, ImageRecord, SearchFilters, SearchResult } from "./types";

type View = "search" | "upload" | "library";
type DetailItem = ImageRecord | SearchResult;
type Message = { tone: "success" | "error" | "info"; text: string } | null;
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  start: () => void;
};

function App() {
  const [view, setView] = useState<View>("search");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<DetailItem | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const [loadingLibrary, setLoadingLibrary] = useState(false);

  const refresh = async () => {
    setLoadingLibrary(true);
    try {
      const [healthData, imageData] = await Promise.all([getHealth(), listImages()]);
      setHealth(healthData);
      setImages(imageData);
    } catch (error) {
      setMessage({ tone: "error", text: errorMessage(error) });
    } finally {
      setLoadingLibrary(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const indexedLabel = useMemo(() => {
    if (!health) {
      return "Backend offline";
    }
    return `${health.indexedImages} indexed · ${health.vectorBackend}`;
  }, [health]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">物忆</p>
          <h1>RecallLens</h1>
        </div>
        <div className="status-cluster">
          <span className={health?.ok ? "status-pill online" : "status-pill offline"}>
            {indexedLabel}
          </span>
          <button className="icon-button" type="button" title="Refresh" onClick={refresh}>
            {loadingLibrary ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
          </button>
        </div>
      </header>

      <nav className="view-tabs" aria-label="Primary">
        <TabButton active={view === "search"} icon={<Search size={18} />} onClick={() => setView("search")}>
          Search
        </TabButton>
        <TabButton active={view === "upload"} icon={<UploadCloud size={18} />} onClick={() => setView("upload")}>
          Upload
        </TabButton>
        <TabButton active={view === "library"} icon={<Images size={18} />} onClick={() => setView("library")}>
          Library
        </TabButton>
      </nav>

      {message && (
        <div className={`message ${message.tone}`}>
          <span>{message.text}</span>
          <button type="button" title="Dismiss" onClick={() => setMessage(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      <section className="workspace">
        <div className="primary-pane">
          {view === "search" && (
            <SearchPanel
              results={results}
              onResults={setResults}
              onSelect={setSelected}
              onMessage={setMessage}
            />
          )}
          {view === "upload" && (
            <UploadPanel
              onUploaded={(record) => {
                setImages((current) => [record, ...current]);
                setSelected(record);
                setMessage({ tone: "success", text: "Photo indexed." });
                refresh();
              }}
              onMessage={setMessage}
            />
          )}
          {view === "library" && (
            <LibraryPanel images={images} loading={loadingLibrary} onSelect={setSelected} />
          )}
        </div>
        <DetailPanel item={selected} onClose={() => setSelected(null)} />
      </section>
    </main>
  );
}

function TabButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className={active ? "tab active" : "tab"} type="button" onClick={onClick}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

function SearchPanel({
  results,
  onResults,
  onSelect,
  onMessage,
}: {
  results: SearchResult[];
  onResults: (results: SearchResult[]) => void;
  onSelect: (item: SearchResult) => void;
  onMessage: (message: Message) => void;
}) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(5);
  const [filters, setFilters] = useState<SearchFilters>({});
  const [searching, setSearching] = useState(false);
  const [listening, setListening] = useState(false);

  const runSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) {
      onMessage({ tone: "error", text: "Enter a search query." });
      return;
    }

    setSearching(true);
    try {
      const response = await searchImages(query, limit, filters);
      onResults(response.results);
      if (response.results.length === 0) {
        onMessage({ tone: "info", text: "No matching photos yet." });
      }
    } catch (error) {
      onMessage({ tone: "error", text: errorMessage(error) });
    } finally {
      setSearching(false);
    }
  };

  const startVoiceInput = () => {
    const speechWindow = window as Window & {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const SpeechRecognition =
      speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      onMessage({ tone: "error", text: "Voice input is unavailable in this browser." });
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => {
      setListening(false);
      onMessage({ tone: "error", text: "Voice input stopped." });
    };
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) {
        setQuery(transcript);
      }
    };
    recognition.start();
  };

  return (
    <section className="tool-panel">
      <form className="search-form" onSubmit={runSearch}>
        <label className="query-box">
          <Search size={22} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="我的钥匙在哪？"
            autoFocus
          />
        </label>
        <button
          className="secondary-button"
          type="button"
          title="Voice search"
          onClick={startVoiceInput}
          disabled={listening}
        >
          {listening ? <Loader2 className="spin" size={18} /> : <Mic size={18} />}
          <span>{listening ? "Listening" : "Voice"}</span>
        </button>
        <button className="primary-button" type="submit" disabled={searching}>
          {searching ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
          <span>Search</span>
        </button>
      </form>

      <div className="filter-row">
        <label>
          <SlidersHorizontal size={16} />
          <span>Top</span>
          <input
            type="number"
            min="1"
            max="30"
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          />
        </label>
        <label>
          <Clock3 size={16} />
          <span>From</span>
          <input
            type="date"
            value={filters.capturedFrom ?? ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, capturedFrom: event.target.value }))
            }
          />
        </label>
        <label>
          <Clock3 size={16} />
          <span>To</span>
          <input
            type="date"
            value={filters.capturedTo ?? ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, capturedTo: event.target.value }))
            }
          />
        </label>
        <label>
          <MapPin size={16} />
          <span>Place</span>
          <input
            value={filters.locationText ?? ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, locationText: event.target.value }))
            }
            placeholder="desk"
          />
        </label>
      </div>

      <ResultGrid results={results} onSelect={onSelect} />
    </section>
  );
}

function UploadPanel({
  onUploaded,
  onMessage,
}: {
  onUploaded: (record: ImageRecord) => void;
  onMessage: (message: Message) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [locationLabel, setLocationLabel] = useState("");
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const locate = () => {
    if (!navigator.geolocation) {
      onMessage({ tone: "error", text: "Geolocation is unavailable in this browser." });
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude);
        setLongitude(position.coords.longitude);
        setLocating(false);
      },
      (error) => {
        onMessage({ tone: "error", text: error.message });
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      onMessage({ tone: "error", text: "Choose a photo first." });
      return;
    }

    const formData = new FormData();
    formData.append("image", file);
    appendIfPresent(formData, "note", note);
    appendIfPresent(formData, "capturedAt", capturedAt);
    appendIfPresent(formData, "locationLabel", locationLabel);
    if (latitude !== null) {
      formData.append("latitude", String(latitude));
    }
    if (longitude !== null) {
      formData.append("longitude", String(longitude));
    }

    setSubmitting(true);
    try {
      const record = await uploadImage(formData);
      setFile(null);
      setNote("");
      setCapturedAt("");
      setLocationLabel("");
      setLatitude(null);
      setLongitude(null);
      onUploaded(record);
    } catch (error) {
      onMessage({ tone: "error", text: errorMessage(error) });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="tool-panel">
      <form className="upload-form" onSubmit={submit}>
        <label className={preview ? "photo-drop has-preview" : "photo-drop"}>
          {preview ? (
            <img src={preview} alt="Selected upload preview" />
          ) : (
            <>
              <ImagePlus size={38} />
              <span>Choose photo</span>
            </>
          )}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>

        <div className="field-grid">
          <label>
            <span>Captured</span>
            <input
              type="datetime-local"
              value={capturedAt}
              onChange={(event) => setCapturedAt(event.target.value)}
            />
          </label>
          <label>
            <span>Place</span>
            <input
              value={locationLabel}
              onChange={(event) => setLocationLabel(event.target.value)}
              placeholder="entry shelf"
            />
          </label>
          <label className="wide-field">
            <span>Notes</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="keys beside the mail tray"
              rows={4}
            />
          </label>
        </div>

        <div className="upload-actions">
          <button className="secondary-button" type="button" onClick={locate} disabled={locating}>
            {locating ? <Loader2 className="spin" size={18} /> : <LocateFixed size={18} />}
            <span>{latitude !== null && longitude !== null ? "GPS saved" : "Use GPS"}</span>
          </button>
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? <Loader2 className="spin" size={18} /> : <UploadCloud size={18} />}
            <span>Index Photo</span>
          </button>
        </div>
      </form>
    </section>
  );
}

function LibraryPanel({
  images,
  loading,
  onSelect,
}: {
  images: ImageRecord[];
  loading: boolean;
  onSelect: (item: ImageRecord) => void;
}) {
  if (loading) {
    return (
      <section className="empty-state">
        <Loader2 className="spin" size={24} />
        <span>Loading library</span>
      </section>
    );
  }

  if (images.length === 0) {
    return (
      <section className="empty-state">
        <Images size={28} />
        <span>No photos indexed yet.</span>
      </section>
    );
  }

  return (
    <section className="tool-panel">
      <div className="library-grid">
        {images.map((image) => (
          <button className="image-card" key={image.id} type="button" onClick={() => onSelect(image)}>
            <img src={mediaUrl(image.thumbnailUrl)} alt={image.originalFilename} />
            <CardText item={image} />
          </button>
        ))}
      </div>
    </section>
  );
}

function ResultGrid({
  results,
  onSelect,
}: {
  results: SearchResult[];
  onSelect: (item: SearchResult) => void;
}) {
  if (results.length === 0) {
    return (
      <div className="empty-state results-empty">
        <Camera size={28} />
        <span>Search results will appear here.</span>
      </div>
    );
  }

  return (
    <div className="library-grid">
      {results.map((result) => (
        <button
          className="image-card result-card"
          key={result.imageId}
          type="button"
          onClick={() => onSelect(result)}
        >
          <img src={mediaUrl(result.thumbnailUrl)} alt={result.originalFilename} />
          <div className="score-badge">{Math.round(result.score * 100)}%</div>
          <CardText item={result} />
        </button>
      ))}
    </div>
  );
}

function DetailPanel({ item, onClose }: { item: DetailItem | null; onClose: () => void }) {
  if (!item) {
    return (
      <aside className="detail-pane idle">
        <ImageIcon size={30} />
        <span>Select a photo</span>
      </aside>
    );
  }

  const imageUrl = mediaUrl(item.imageUrl);
  const place = formatLocation(item.location);

  return (
    <aside className="detail-pane">
      <div className="detail-toolbar">
        <button type="button" title="Close" onClick={onClose}>
          <X size={18} />
        </button>
        <a href={imageUrl} target="_blank" rel="noreferrer" title="Open original">
          <ExternalLink size={18} />
        </a>
      </div>
      <img className="detail-image" src={imageUrl} alt={item.originalFilename} />
      <div className="detail-copy">
        <h2>{item.originalFilename}</h2>
        <p>{item.userNotes || "No notes."}</p>
        <dl>
          {item.description && (
            <div>
              <dt>Tags</dt>
              <dd>{formatDescription(item.description)}</dd>
            </div>
          )}
          <div>
            <dt>
              <Clock3 size={15} />
              Time
            </dt>
            <dd>{formatDate(item.capturedAt ?? item.uploadTime)}</dd>
          </div>
          <div>
            <dt>
              <MapPin size={15} />
              Place
            </dt>
            <dd>{place}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{item.indexStatus}</dd>
          </div>
          <div>
            <dt>Embedding</dt>
            <dd>{formatEmbedding(item)}</dd>
          </div>
        </dl>
      </div>
    </aside>
  );
}

function CardText({ item }: { item: DetailItem }) {
  return (
    <span className="card-copy">
      <strong>{item.userNotes || item.originalFilename}</strong>
      <span>{formatDate(item.capturedAt ?? item.uploadTime)}</span>
      <span>{formatLocation(item.location)}</span>
    </span>
  );
}

function appendIfPresent(formData: FormData, key: string, value: string) {
  const trimmed = value.trim();
  if (trimmed) {
    formData.append(key, trimmed);
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function formatDate(value: string | null): string {
  if (!value) {
    return "No time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatLocation(location: { latitude: number | null; longitude: number | null; label: string | null }) {
  if (location.label) {
    return location.label;
  }
  if (location.latitude !== null && location.longitude !== null) {
    return `${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`;
  }
  return "No location";
}

function formatDescription(value: string): string {
  return value.replace(/^Semantic tags:\s*/i, "").replace(/\.$/, "");
}

function formatEmbedding(item: {
  embeddingModel: string | null;
  embeddingDimension: number | null;
  embeddingNorm: number | null;
}) {
  if (!item.embeddingModel && item.embeddingDimension === null) {
    return "No embedding metadata";
  }
  const parts = [
    item.embeddingModel,
    item.embeddingDimension !== null ? `${item.embeddingDimension}d` : null,
    item.embeddingNorm !== null ? `norm ${item.embeddingNorm}` : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

export default App;
