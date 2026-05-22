import { env } from "@/env";

export interface SessionDTO {
  id: string;
  name: string;
  state: string;
  created_at: string;
}

export type CardState =
  | "verified"
  | "partial"
  | "disputed"
  | "unverified"
  | "opinion"
  | "heads_up"
  | "pending";

export type CardSource = "auto" | "manual";
export type CardZone = "critical" | "calm";

export interface FactCardDTO {
  id: string;
  claim_text: string;
  claim_type: string;
  state: CardState;
  verdict?: string | null;
  correction?: string | null;
  confidence?: number | null;
  sources: Array<{
    url: string;
    title: string | null;
    publisher: string | null;
    published_at: string | null;
    rank: number;
  }>;
  pinned: boolean;
  source: CardSource;
  zone: CardZone;
  query_echo: string | null;
  /// Who said the claim — "You" (host) or "Guest". null for manual (Ask
  /// Glass) and anticipatory heads-up cards.
  speaker?: string | null;
  /// ISO timestamp of when the claim was detected from the transcript.
  /// Present on history cards (GET /cards); absent on live WS cards, where
  /// the client falls back to card arrival time.
  detected_at?: string | null;
}

export interface SessionListItemDTO {
  id: string;
  name: string;
  state: string;
  created_at: string;
  ended_at: string | null;
  card_count: number;
  disputed_count: number;
}

export interface TranscriptLineDTO {
  id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  speaker: string | null;
}

export type CardAction = "dismissed" | "sent_to_overlay" | "saved";

type FetchOpts = RequestInit & { token: string };

async function jfetch<T>(path: string, opts: FetchOpts): Promise<T> {
  const res = await fetch(`${env.apiBase}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.token}`,
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}`);
  }
  return (await res.json()) as T;
}

export const api = {
  createSession: (name: string, token: string) =>
    jfetch<SessionDTO>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name }),
      token,
    }),
  getSession: (id: string, token: string) =>
    jfetch<SessionDTO>(`/api/sessions/${id}`, { token }),
  endSession: (id: string, token: string) =>
    jfetch<SessionDTO>(`/api/sessions/${id}/end`, { method: "POST", token }),
  cardAction: (
    sessionId: string,
    cardId: string,
    action: CardAction,
    token: string,
  ) =>
    jfetch<{ status: string }>(
      `/api/sessions/${sessionId}/cards/${cardId}/action`,
      { method: "POST", body: JSON.stringify({ action }), token },
    ),
  getSessionCards: (sessionId: string, token: string) =>
    jfetch<FactCardDTO[]>(`/api/sessions/${sessionId}/cards`, { token }),
  listSessions: (token: string) =>
    jfetch<SessionListItemDTO[]>("/api/sessions", { token }),
  getSessionTranscript: (sessionId: string, token: string) =>
    jfetch<TranscriptLineDTO[]>(
      `/api/sessions/${sessionId}/transcript`,
      { token },
    ),
  setupSession: (
    sessionId: string,
    docket: string,
    anticipationC: boolean,
    token: string,
  ) =>
    jfetch<{ state: string; entities_count: number }>(
      `/api/sessions/${sessionId}/setup`,
      {
        method: "POST",
        body: JSON.stringify({ docket, anticipation_c: anticipationC }),
        token,
      },
    ),
  pinCard: (sessionId: string, cardId: string, pinned: boolean, token: string) =>
    jfetch<{ status: string; pinned: boolean }>(
      `/api/sessions/${sessionId}/cards/${cardId}/pin`,
      { method: "POST", body: JSON.stringify({ pinned }), token },
    ),
  ask: (
    sessionId: string,
    body: { query: string } | { action: "verify_last" | "rescan_30s" },
    token: string,
  ) =>
    jfetch<{ job_id: string; accepted_at: string }>(
      `/api/sessions/${sessionId}/ask`,
      { method: "POST", body: JSON.stringify(body), token },
    ),
  stopSession: (sessionId: string, token: string) =>
    jfetch<SessionDTO>(`/api/sessions/${sessionId}/stop`, {
      method: "POST",
      token,
    }),
};
