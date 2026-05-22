import { create } from "zustand";

/// Combined audio activity for the top-bar pulse bar.
///
/// `combinedRMS` is `min(1, hypot(mic, sys))`. Goes flat (0) after 1s without
/// a new RMS frame — that's the visual cue that the helper disconnected or
/// audio stopped flowing (per Plan C Task 6).
interface AudioState {
  combinedRMS: number;
  lastRMSAt: number;
  staleTimer: ReturnType<typeof setTimeout> | null;
  setRMS: (mic: number, sys: number) => void;
  reset: () => void;
}

export const useAudioStore = create<AudioState>()((set, get) => ({
  combinedRMS: 0,
  lastRMSAt: 0,
  staleTimer: null,
  setRMS: (mic, sys) => {
    const combined = Math.min(1, Math.hypot(mic, sys));
    const existing = get().staleTimer;
    if (existing) clearTimeout(existing);
    const timer = setTimeout(() => {
      set({ combinedRMS: 0, staleTimer: null });
    }, 1000);
    set({ combinedRMS: combined, lastRMSAt: Date.now(), staleTimer: timer });
  },
  reset: () => {
    const existing = get().staleTimer;
    if (existing) clearTimeout(existing);
    set({ combinedRMS: 0, lastRMSAt: 0, staleTimer: null });
  },
}));
