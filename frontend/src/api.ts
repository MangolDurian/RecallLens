import type { HealthResponse, ImageRecord, SearchFilters, SearchResponse } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    if (text) {
      try {
        const body = JSON.parse(text);
        message = body.detail ?? message;
      } catch {
        message = text;
      }
    }
    throw new Error(message || "Request failed.");
  }
  return (text ? JSON.parse(text) : null) as T;
}

export function mediaUrl(path: string): string {
  if (path.startsWith("http")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/api/health`);
  return parseResponse<HealthResponse>(response);
}

export async function listImages(): Promise<ImageRecord[]> {
  const response = await fetch(`${API_BASE}/api/images`);
  return parseResponse<ImageRecord[]>(response);
}

export async function getImage(id: string): Promise<ImageRecord> {
  const response = await fetch(`${API_BASE}/api/images/${id}`);
  return parseResponse<ImageRecord>(response);
}

export async function uploadImage(formData: FormData): Promise<ImageRecord> {
  const response = await fetch(`${API_BASE}/api/images`, {
    method: "POST",
    body: formData,
  });
  return parseResponse<ImageRecord>(response);
}

export async function searchImages(
  queryText: string,
  limit: number,
  filters: SearchFilters,
): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      queryText,
      limit,
      capturedFrom: filters.capturedFrom || null,
      capturedTo: filters.capturedTo || null,
      locationText: filters.locationText || null,
    }),
  });
  return parseResponse<SearchResponse>(response);
}
