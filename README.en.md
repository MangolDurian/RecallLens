[中文](README.md)

# RecallLens

**Local-first visual memory index for everyday objects** — Upload a photo, search later with natural language to quickly find your things.

Supports queries like "where are my keys?", "blue backpack", or "passport drawer" in both English and Chinese.

## Highlights

- **Local CLIP semantic retrieval** — Automatic vector embeddings for images with natural language search, no cloud API required
- **Zero-shot semantic tags** — Automatically identifies object type, scene, and color, saved into each image description
- **Hybrid ranking** — Vector semantic matching + weighted boosts from filenames, notes, tags, and location text
- **Smart date inference** — Automatically infers date ranges from query text (today, yesterday, this week, last N days)
- **PWA offline support** — React frontend + static fallback UI, both installable as PWAs

## Architecture

```mermaid
%%{init:{"theme":"base","themeVariables":{"primaryTextColor":"#0a1f3d","lineColor":"#90a4ae","fontFamily":"system-ui,sans-serif","fontSize":"13px"}}}%%
graph TB
    classDef fe fill:#dce5ef,stroke:#3a6b9f,stroke-width:1.4px,color:#0a1f3d
    classDef be fill:#e2e8f0,stroke:#4a6278,stroke-width:1.4px,color:#0a1f3d
    classDef db fill:#ede8e0,stroke:#7d6e5d,stroke-width:1.4px,color:#0a1f3d
    classDef ai fill:#e6dfe8,stroke:#6b4d7a,stroke-width:1.4px,color:#0a1f3d

    subgraph Frontend["Frontend"]
        A(["React PWA"]):::fe
        B(["Static Fallback UI"]):::fe
    end

    subgraph Backend["Backend · FastAPI"]
        C["API Routes"]:::be
        D["RecallLens Service"]:::be
    end

    subgraph Data["Data Layer"]
        E[("SQLite")]:::db
        F["Local Image Storage"]:::db
        G["Vector Index · FAISS / NumPy"]:::db
    end

    subgraph Model["AI Models"]
        H["CLIP · open_clip_torch"]:::ai
        I["Semantic Labeler"]:::ai
    end

    A --> C
    B --> C
    C --> D
    D --> E
    D --> F
    D --> G
    D --> H
    H --> I
```

## Quick Start

```bash
# Install dependencies (including CLIP)
uv sync --extra test
uv pip install -r requirements-clip.txt

# Start backend
uv run uvicorn backend.app.main:app --reload --port 8000
```

Open `http://localhost:8000/app/` to get started.

Quick start without CLIP:

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

## Upload Flow

```mermaid
%%{init:{"theme":"base","themeVariables":{"primaryTextColor":"#0a1f3d","lineColor":"#7a8f9e","actorTextColor":"#0a1f3d","actorBkg":"#dce5ef","actorBorder":"#3a6b9f","actorLineColor":"#7a8f9e","noteBkgColor":"#f5f0eb","noteTextColor":"#0a1f3d","noteBorderColor":"#a09080","labelBoxBkgColor":"#e2e8f0","labelBoxBorderColor":"#4a6278","labelTextColor":"#0a1f3d","loopTextColor":"#0a1f3d","fontFamily":"system-ui,sans-serif","fontSize":"13px"}}}%%
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant S as Storage
    participant E as CLIP Encoder
    participant L as Semantic Labeler
    participant V as Vector Index
    participant DB as SQLite

    U->>API: POST /api/images (image + optional metadata)
    rect rgba(220, 229, 239, 0.15)
        API->>S: Save original + generate thumbnail
        S->>DB: Insert image record (status: processing)
    end
    rect rgba(230, 223, 232, 0.2)
        S->>E: Encode image vector
        E->>L: Generate semantic tags (object / scene / color)
        E->>V: Add to vector index
    end
    rect rgba(237, 232, 224, 0.15)
        V->>DB: Update record (status: indexed)
    end
    API-->>U: Return image record + metadata
```

## Search Flow

```mermaid
%%{init:{"theme":"base","themeVariables":{"primaryTextColor":"#0a1f3d","lineColor":"#7a8f9e","fontFamily":"system-ui,sans-serif","fontSize":"13px"}}}%%
flowchart LR
    classDef input fill:#dce5ef,stroke:#3a6b9f,stroke-width:1.4px,color:#0a1f3d
    classDef process fill:#e2e8f0,stroke:#4a6278,stroke-width:1.4px,color:#0a1f3d
    classDef decision fill:#f5f0eb,stroke:#7d6e5d,stroke-width:1.4px,color:#0a1f3d
    classDef score fill:#e6dfe8,stroke:#6b4d7a,stroke-width:1.4px,color:#0a1f3d
    classDef result fill:#dce5ef,stroke:#3a6b9f,stroke-width:1.4px,color:#0a1f3d

    A["Query Text"]:::input --> B["CLIP Encode Vector"]:::process
    B --> C["Vector Index Top-K"]:::process
    C --> D{"Parse Filters"}:::decision
    D -->|"Explicit"| E["capturedFrom / To<br/>locationText"]:::process
    D -->|"Not specified"| F["Infer Date Range"]:::process
    E --> G["Filter Candidates"]:::process
    F --> G
    G --> H["Hybrid Scoring"]:::score
    H --> I["Vector Match × 0.65"]:::score
    H --> J["Metadata Boost"]:::score
    I --> K["Merge & Sort Top-N"]:::result
    J --> K
    K --> L["Save Query Record"]:::result
    L --> M["Return Results"]:::result
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React, Vite, TypeScript, PWA |
| Backend | FastAPI, SQLite, local image storage |
| Retrieval | Local CLIP embeddings, FAISS optional |
| Image Understanding | CLIP zero-shot semantic tags |
| Test/Demo | Deterministic hash embeddings (dev & test only) |

## Project Structure

```
backend/
  app/          FastAPI application
  tests/        Backend API and retrieval tests
frontend/
  src/          React PWA source
  public/       manifest, icon, service worker
static/         No-build fallback PWA served at /app/
data/           Local runtime data, ignored by git
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/images` | Upload image (multipart or JSON base64) |
| `GET` | `/api/images` | List images by newest first |
| `GET` | `/api/images/{id}` | Get single image record |
| `POST` | `/api/search` | Natural language search |
| `GET` | `/api/queries` | Search history |
| `GET` | `/api/tags` | Semantic tag groups |
| `GET` | `/api/health` | Service status |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `RECALLLENS_DATA_DIR` | `./data` | Data storage directory |
| `RECALLLENS_EMBEDDER` | `clip` | Embedding backend (`clip` or `hash`) |
| `RECALLLENS_CLIP_MODEL` | `ViT-B-32` | CLIP model name |
| `RECALLLENS_CLIP_PRETRAINED` | `laion2b_s34b_b79k` | CLIP pretrained weights |

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Defaults to API at `http://localhost:8000`:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Demo Dataset

Try the full upload/index/search flow without CLIP weights:

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/seed_demo.py --data-dir data/demo
RECALLLENS_EMBEDDER=hash RECALLLENS_DATA_DIR=data/demo uv run uvicorn backend.app.main:app --reload --port 8000
```

Try searching: `keys entry shelf`, `blue backpack`, `passport drawer`, `charger nightstand`

## Tests

```bash
uv sync --extra test
RECALLLENS_EMBEDDER=hash uv run pytest
```

Quick smoke tests:

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_backend.py
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_api.py
```
