import { describe, it, expect, beforeEach, vi } from "vitest";

import { useAudioStore } from "@/stores/audio_store";

describe("useAudioStore", () => {
  beforeEach(() => {
    useAudioStore.getState().reset();
    vi.useFakeTimers();
  });

  it("setRMS produces combined = hypot(mic, sys) clamped to 1", () => {
    useAudioStore.getState().setRMS(0.3, 0.4);
    const v = useAudioStore.getState().combinedRMS;
    expect(v).toBeCloseTo(Math.min(1, Math.hypot(0.3, 0.4)), 5);
  });

  it("clamps to 1 for loud combined input", () => {
    useAudioStore.getState().setRMS(2.0, 0.0);
    expect(useAudioStore.getState().combinedRMS).toBe(1);
  });

  it("flattens to 0 after 1s of staleness", () => {
    useAudioStore.getState().setRMS(0.5, 0.0);
    expect(useAudioStore.getState().combinedRMS).toBeGreaterThan(0);
    vi.advanceTimersByTime(1100);
    expect(useAudioStore.getState().combinedRMS).toBe(0);
  });

  it("resets the stale timer on each new setRMS", () => {
    useAudioStore.getState().setRMS(0.5, 0.0);
    vi.advanceTimersByTime(900);
    // Still alive — refresh
    useAudioStore.getState().setRMS(0.4, 0.0);
    vi.advanceTimersByTime(900);
    // Total elapsed = 1.8s but timer was reset at 0.9s, so still alive
    expect(useAudioStore.getState().combinedRMS).toBeGreaterThan(0);
    vi.advanceTimersByTime(200);
    expect(useAudioStore.getState().combinedRMS).toBe(0);
  });

  it("reset clears the timer and RMS", () => {
    useAudioStore.getState().setRMS(0.5, 0.5);
    useAudioStore.getState().reset();
    expect(useAudioStore.getState().combinedRMS).toBe(0);
    expect(useAudioStore.getState().lastRMSAt).toBe(0);
    expect(useAudioStore.getState().staleTimer).toBe(null);
  });
});
