export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

type Init = Omit<RequestInit, "body"> & { json?: unknown };

const WRITE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function detailOf(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  }
  return status >= 500 ? "o servidor não respondeu, tente de novo" : `erro ${status}`;
}

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const method = (init.method ?? (init.json !== undefined ? "POST" : "GET")).toUpperCase();
  const headers = new Headers(init.headers);
  if (WRITE.has(method)) headers.set("X-Voryx-CSRF", "1");
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, method, headers, body, credentials: "include" });
  } catch {
    throw new ApiError(0, "sem conexão com o servidor");
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.location.href = "/login";
  }
  if (!res.ok) throw new ApiError(res.status, detailOf(data, res.status));
  return data as T;
}

export type Media = { id: number; mime: string; size: number };

export function upload(file: File, onProgress?: (pct: number) => void): Promise<Media> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/media`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-Voryx-CSRF", "1");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* empty */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as Media);
      else reject(new ApiError(xhr.status, detailOf(data, xhr.status)));
    };
    xhr.onerror = () => reject(new ApiError(0, "o envio falhou (arquivo grande demais ou sem conexão)"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
