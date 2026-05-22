import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export interface TranscriptLine {
  id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  speaker_label: string;
}

interface State {
  sessionId: string | null;
  partial: { text: string; speaker_label: string } | null;
  lines: TranscriptLine[];

  setSession: (id: string | null) => void;
  setPartial: (p: { text: string; speaker_label: string } | null) => void;
  appendLine: (line: TranscriptLine) => void;
  reset: () => void;
}

export const useSessionStore = create<State>()(
  subscribeWithSelector((set) => ({
    sessionId: null,
    partial: null,
    lines: [],

    setSession: (id) => set({ sessionId: id, lines: [], partial: null }),
    setPartial: (p) => set({ partial: p }),
    appendLine: (line) =>
      set((s) => ({ lines: [...s.lines, line], partial: null })),
    reset: () => set({ sessionId: null, lines: [], partial: null }),
  })),
);
