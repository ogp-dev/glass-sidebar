import { env } from "@/env";

import type { CardSource, CardState, CardZone } from "@/lib/api";

export type DashboardEvent =
  | {
      kind: "transcript_partial";
      text: string;
      start_ms: number;
      end_ms: number;
      speaker_label: string;
    }
  | {
      kind: "transcript_line";
      id: string;
      text: string;
      start_ms: number;
      end_ms: number;
      speaker_label: string;
    }
  | {
      kind: "card";
      id: string;
      claim_text: string;
      claim_type: string;
      state: CardState;
      verdict: string | null;
      correction: string | null;
      confidence: number | null;
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
      speaker?: string | null;
    }
  | {
      kind: "card_updated";
      id: string;
      pinned: boolean;
    }
  | {
      kind: "rms";
      mic: number;
      sys: number;
    }
  | {
      kind: "helper_status";
      connected: boolean;
    };

export interface DashboardSocketOpts {
  sessionId: string;
  onEvent: (e: DashboardEvent) => void;
  onStatus?: (s: "connecting" | "open" | "closed" | "error") => void;
}

export function openDashboardSocket(opts: DashboardSocketOpts): () => void {
  let closed = false;
  let attempt = 0;
  let socket: WebSocket | null = null;

  const url = `${env.wsBase || ""}/ws/dashboard/${opts.sessionId}`;

  function connect(): void {
    opts.onStatus?.("connecting");
    socket = new WebSocket(url);
    socket.onopen = () => {
      attempt = 0;
      opts.onStatus?.("open");
    };
    socket.onmessage = (e) => {
      try {
        opts.onEvent(JSON.parse(e.data as string) as DashboardEvent);
      } catch {
        /* ignore malformed */
      }
    };
    socket.onerror = () => opts.onStatus?.("error");
    socket.onclose = () => {
      opts.onStatus?.("closed");
      if (closed) return;
      // exponential backoff with jitter, capped at 30s
      const delay = Math.min(30_000, 500 * 2 ** attempt) + Math.random() * 300;
      attempt += 1;
      setTimeout(connect, delay);
    };
  }

  connect();

  return () => {
    closed = true;
    socket?.close();
  };
}
