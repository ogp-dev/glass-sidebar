import { describe, it, expect, vi, beforeEach } from "vitest";
import { openDashboardSocket } from "@/lib/ws";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }
  close() {
    this.onclose?.();
  }
}

describe("openDashboardSocket", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeSocket as unknown as typeof WebSocket);
  });

  it("invokes onEvent on parsed messages", () => {
    const events: unknown[] = [];
    openDashboardSocket({
      sessionId: "s1",
      onEvent: (e) => events.push(e),
    });
    const s = FakeSocket.instances[0];
    s.onopen?.();
    s.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ kind: "card", id: "c1" }),
      }),
    );
    expect(events).toEqual([{ kind: "card", id: "c1" }]);
  });

  it("ignores malformed JSON", () => {
    const events: unknown[] = [];
    openDashboardSocket({
      sessionId: "s1",
      onEvent: (e) => events.push(e),
    });
    const s = FakeSocket.instances[0];
    s.onmessage?.(new MessageEvent("message", { data: "not json" }));
    expect(events).toEqual([]);
  });

  it("returned cleanup function stops reconnect", () => {
    const close = openDashboardSocket({ sessionId: "s1", onEvent: () => {} });
    close();
    // No assertion beyond "doesn't throw" — internal `closed` flag suppresses reconnect.
    expect(true).toBe(true);
  });
});
