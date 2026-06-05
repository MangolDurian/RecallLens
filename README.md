# RecallLens

RecallLens is a local-first visual memory index for everyday objects. Upload a photo, add optional context, and search later with natural language such as "where are my keys?" or "blue backpack".

## Stack

- Frontend: React, Vite, TypeScript, PWA assets
- Backend: FastAPI, SQLite, local image storage
- Retrieval: local CLIP embeddings with FAISS when available
- Image understanding: CLIP zero-shot semantic tags saved into each image description
- Test/dev fallback: deterministic hash embeddings, used only when explicitly configured

## Project Layout

```text
backend/
  app/          FastAPI application
  tests/        backend API and retrieval tests
frontend/
  src/          React PWA source
  public/       manifest, icon, service worker
static/         no-build fallback PWA served at /app/
data/           local runtime data, ignored by git
```

## API

- `POST /api/images`: multipart upload with `image`, optional `note`, `capturedAt`, `latitude`, `longitude`, `locationLabel`; also accepts JSON `imageBase64` for the fallback UI.
- `GET /api/images`: list local image records by newest captured/upload time.
- `GET /api/images/{id}`: fetch one image record and media URLs.
- `POST /api/search`: natural language search with `queryText`, optional `limit`, `capturedFrom`, `capturedTo`, and `locationText`.
- `GET /api/queries`: recent search history with stored query embeddings and result IDs.
- `GET /api/tags`: generated semantic tag groups for quick browsing.
- `GET /api/health`: backend, embedding, and vector index status.

## Backend Setup

```bash
uv sync --extra test
uv pip install -r requirements-clip.txt
uv run uvicorn backend.app.main:app --reload --port 8000
```

The default embedding backend is local CLIP through `open_clip_torch`. The first real upload/search may download model weights if they are not already cached. Each uploaded image is embedded and compared against a small built-in label bank, so the stored `description` field contains semantic tags such as object type, likely scene, and color. For API tests without CLIP, install only `--extra test`.

When a photo includes EXIF metadata, RecallLens uses it as a fallback for captured time and GPS coordinates. Values entered by the user or provided by the browser take precedence over EXIF.

Search can also infer simple date ranges from the query when explicit filters are not provided. Supported phrases include `today`, `yesterday`, `this week`, `last week`, `last 7 days`, `今天`, `昨天`, `本周`, `上周`, and `最近 N 天`.

Search ranking is hybrid: image vectors provide the main semantic match, while filenames, user notes, semantic tags, and location labels provide small ranking boosts. This makes personal hints like `passport drawer` or `office backpack` useful without replacing visual retrieval.

Each search is saved as a Query Record containing the query text, query embedding, filters, and result image IDs. Query history is available at `GET /api/queries`.

Each image response also exposes embedding metadata (`embeddingModel`, `embeddingDimension`, and `embeddingNorm`) so you can audit which model indexed a photo and whether the vector shape is correct.

Semantic tags are grouped automatically at `GET /api/tags`; the static fallback UI includes a Tags view for quick browsing by generated object, scene, and color labels.

The React and static fallback UIs include optional voice query input through the browser Web Speech API. Browsers that do not expose speech recognition continue to work with typed search.

Useful environment variables:

```bash
RECALLLENS_DATA_DIR=./data
RECALLLENS_EMBEDDER=clip
RECALLLENS_CLIP_MODEL=ViT-B-32
RECALLLENS_CLIP_PRETRAINED=laion2b_s34b_b79k
```

For fast local API testing without CLIP:

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

The hash backend is deterministic and useful for testing the upload/search flow, but it is not a substitute for real CLIP retrieval quality.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend expects the API at `http://localhost:8000` by default. Override with:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## No-build Fallback UI

If npm dependencies are unavailable, use the static fallback UI:

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

Then open `http://localhost:8000/app/`. You can also open `static/index.html` directly in a browser and leave the API field set to `http://localhost:8000`.

The fallback UI uploads images as JSON/base64, so it can work even before `python-multipart` is installed. Multipart uploads remain supported by the same `/api/images` endpoint after installing the normal backend dependencies.

The fallback UI also includes its own manifest, icon, and service worker under `/app/`. It can be installed as a small PWA and can reopen the interface while offline; upload, search, media, and metadata still require the local FastAPI backend to be running.

## Demo Dataset

To try the full upload/index/search flow quickly without CLIP weights, seed ten local object photos into an isolated demo library:

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/seed_demo.py --data-dir data/demo
RECALLLENS_EMBEDDER=hash RECALLLENS_DATA_DIR=data/demo uv run uvicorn backend.app.main:app --reload --port 8000
```

Then open `http://localhost:8000/app/` and search for examples like `keys entry shelf`, `blue backpack`, `passport drawer`, or `charger nightstand`. Re-running the seed command reuses existing demo records; add `--reset` only when you want to recreate `data/demo` from scratch.

## Tests

```bash
uv sync --extra test
RECALLLENS_EMBEDDER=hash uv run pytest
```

The tests use the hash embedding backend so they can run without model weights or network access.

For a quick backend smoke test without pytest:

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_backend.py
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_api.py
```
