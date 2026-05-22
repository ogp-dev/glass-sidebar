import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "@/stores/session_store";

describe("session_store", () => {
  beforeEach(() => useSessionStore.getState().reset());

  it("appends transcript lines and clears partial", () => {
    const s = useSessionStore.getState();
    s.setPartial({ text: "hel", speaker_label: "Speaker 0" });
    s.appendLine({
      id: "1",
      text: "hello",
      start_ms: 0,
      end_ms: 100,
      speaker_label: "Speaker 0",
    });
    const after = useSessionStore.getState();
    expect(after.lines).toHaveLength(1);
    expect(after.partial).toBeNull();
  });

  it("setSession clears lines + partial", () => {
    const s = useSessionStore.getState();
    s.appendLine({
      id: "x",
      text: "y",
      start_ms: 0,
      end_ms: 1,
      speaker_label: "Speaker 0",
    });
    s.setSession("new");
    const after = useSessionStore.getState();
    expect(after.sessionId).toBe("new");
    expect(after.lines).toEqual([]);
  });

  it("reset clears everything", () => {
    const s = useSessionStore.getState();
    s.setSession("abc");
    s.appendLine({
      id: "x",
      text: "y",
      start_ms: 0,
      end_ms: 1,
      speaker_label: "Speaker 0",
    });
    s.reset();
    const after = useSessionStore.getState();
    expect(after.sessionId).toBeNull();
    expect(after.lines).toEqual([]);
  });
});
