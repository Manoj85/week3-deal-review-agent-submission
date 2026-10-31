import type {
  ActionBody,
  Proposal,
  Revision,
  SavedReview,
  Summary,
} from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public reviewId?: string,
  ) {
    super(message);
  }
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the API. Check that FastAPI and Vite are running. If a submission was interrupted, refresh saved reviews before creating another.",
      0,
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (e: { loc: string[]; msg: string }) =>
                  `${e.loc.join(".")}: ${e.msg}`,
              )
              .join("; ")
          : detail?.message ||
            `API request failed (${response.status}). Check the backend terminal.`;
    throw new ApiError(message, response.status, detail?.review_id);
  }
  if (data === null)
    throw new ApiError(
      "The API returned an unreadable response. Refresh saved reviews before retrying.",
      response.status,
    );
  return data as T;
}
export const api = {
  health: () => request<{ mode: string }>("/health"),
  list: () => request<Summary[]>("/reviews?limit=100"),
  get: (id: string) =>
    request<SavedReview>(`/reviews/${encodeURIComponent(id)}`),
  history: (id: string) =>
    request<Revision[]>(`/reviews/${encodeURIComponent(id)}/history`),
  create: (body: Proposal) => request<SavedReview>("/reviews", body),
  action: (id: string, body: ActionBody, retry = false) =>
    request<SavedReview>(
      `/reviews/${encodeURIComponent(id)}/${retry ? "retry" : "actions"}`,
      body,
    ),
};
