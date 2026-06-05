export type LocationResponse = {
  latitude: number | null;
  longitude: number | null;
  label: string | null;
};

export type ImageRecord = {
  id: string;
  imageUrl: string;
  thumbnailUrl: string;
  originalFilename: string;
  uploadTime: string;
  capturedAt: string | null;
  location: LocationResponse;
  description: string | null;
  userNotes: string | null;
  embeddingId: string | null;
  embeddingModel: string | null;
  embeddingDimension: number | null;
  embeddingNorm: number | null;
  indexStatus: string;
};

export type SearchResult = {
  imageId: string;
  score: number;
  imageUrl: string;
  thumbnailUrl: string;
  originalFilename: string;
  uploadTime: string;
  capturedAt: string | null;
  location: LocationResponse;
  description: string | null;
  userNotes: string | null;
  embeddingModel: string | null;
  embeddingDimension: number | null;
  embeddingNorm: number | null;
  indexStatus: string;
};

export type SearchResponse = {
  queryText: string;
  results: SearchResult[];
};

export type HealthResponse = {
  ok: boolean;
  embedder: string;
  vectorBackend: string;
  indexedImages: number;
};

export type SearchFilters = {
  capturedFrom?: string;
  capturedTo?: string;
  locationText?: string;
};
