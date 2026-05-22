import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import type { FactCardDTO } from "@/lib/api";
import { useCardsStore } from "@/stores/cards_store";

function mkCard(
  id: string,
  state: FactCardDTO["state"],
  opts: Partial<FactCardDTO> = {},
): FactCardDTO {
  const source = opts.source ?? "auto";
  const zone =
    source === "manual" || state === "disputed" || state === "partial"
      ? "critical"
      : "calm";
  return {
    id,
    claim_text: "c-" + id,
    claim_type: "event",
    state,
    verdict: null,
    correction: null,
    confidence: 80,
    sources: [],
    pinned: opts.pinned ?? false,
    source,
    zone: opts.zone ?? zone,
    query_echo: opts.query_echo ?? null,
    ...opts,
  };
}

describe("useCardsStore state machine", () => {
  beforeEach(() => {
    useCardsStore.getState().reset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-19T00:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("disputed cards land in critical, verified land in calm", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "verified"));
    expect(useCardsStore.getState().critical.map((c) => c.id)).toEqual(["a"]);
    expect(useCardsStore.getState().calm.map((c) => c.id)).toEqual(["b"]);
  });

  it("partial cards land in critical", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("p", "partial"));
    expect(useCardsStore.getState().critical.map((c) => c.id)).toEqual(["p"]);
  });

  it("heads_up, opinion, unverified all land in calm", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("h", "heads_up"));
    s.appendCard(mkCard("o", "opinion"));
    s.appendCard(mkCard("u", "unverified"));
    const st = useCardsStore.getState();
    expect(st.calm.map((c) => c.id).sort()).toEqual(["h", "o", "u"]);
    expect(st.critical).toEqual([]);
  });

  it("4th critical queues when none of the 3 have passed dwell", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "disputed"));
    s.appendCard(mkCard("c", "disputed"));
    s.appendCard(mkCard("d", "disputed"));
    const st = useCardsStore.getState();
    expect(st.critical.map((c) => c.id)).toEqual(["c", "b", "a"]);
    expect(st.queuedCritical.map((c) => c.id)).toEqual(["d"]);
  });

  it("after 20s, oldest non-pinned demotes when new critical arrives", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    vi.advanceTimersByTime(1000);
    s.appendCard(mkCard("b", "disputed"));
    s.appendCard(mkCard("c", "disputed"));
    s.appendCard(mkCard("d", "disputed"));
    // 'd' queued; nothing has reached dwell yet

    vi.advanceTimersByTime(20_000);
    s.tickDwell();

    const st = useCardsStore.getState();
    expect(st.critical.map((c) => c.id)).toEqual(["d", "c", "b"]);
    expect(st.queuedCritical).toEqual([]);
    expect(st.demotedStrip.map((c) => c.id)).toEqual(["a"]);
  });

  it("pinned card never demotes; oldest non-pinned demotes instead", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "disputed"));
    s.appendCard(mkCard("c", "disputed"));
    s.pinCard("a", true);

    vi.advanceTimersByTime(25_000);
    s.appendCard(mkCard("d", "disputed"));

    const st = useCardsStore.getState();
    // 'a' pinned → 'b' (oldest non-pinned) demotes
    expect(st.critical.map((c) => c.id).sort()).toEqual(["a", "c", "d"].sort());
    expect(st.demotedStrip.map((c) => c.id)).toEqual(["b"]);
  });

  it("manual cards always start critical (even with verified state)", () => {
    const s = useCardsStore.getState();
    s.appendCard(
      mkCard("m", "verified", { source: "manual", pinned: true, zone: "critical" }),
    );
    const st = useCardsStore.getState();
    expect(st.critical.map((c) => c.id)).toEqual(["m"]);
    expect(st.calm).toEqual([]);
  });

  it("demoted strip is FIFO with max 5", () => {
    const s = useCardsStore.getState();
    for (let i = 0; i < 8; i++) {
      s.appendCard(mkCard("c" + i, "disputed"));
      vi.advanceTimersByTime(21_000);
      s.tickDwell();
    }
    expect(useCardsStore.getState().demotedStrip.length).toBe(5);
  });

  it("restoreFromDemotedStrip puts card back in critical with fresh dwell", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "disputed"));
    s.appendCard(mkCard("c", "disputed"));
    vi.advanceTimersByTime(25_000);
    s.appendCard(mkCard("d", "disputed"));
    expect(useCardsStore.getState().demotedStrip.map((c) => c.id)).toEqual([
      "a",
    ]);

    s.restoreFromDemotedStrip("a");
    const st = useCardsStore.getState();
    expect(st.critical.map((c) => c.id)).toContain("a");
    // 'a' is back in critical; the original demoted-strip entry is gone.
    // Because critical was already full (d, c, b), restoring 'a' triggers a
    // fresh demotion — the oldest eligible non-pinned card moves to the strip.
    expect(st.demotedStrip.map((c) => c.id)).not.toContain("a");
  });

  it("tickDwell promotes queued card when slot opens", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "disputed"));
    s.appendCard(mkCard("c", "disputed"));
    s.appendCard(mkCard("d", "disputed")); // queued

    vi.advanceTimersByTime(25_000);
    s.tickDwell();

    const st = useCardsStore.getState();
    expect(st.queuedCritical).toEqual([]);
    expect(st.critical.length).toBe(3);
    expect(st.critical.map((c) => c.id)).toContain("d");
  });

  it("de-dupes by id across all buckets", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("a", "disputed"));
    expect(useCardsStore.getState().critical.length).toBe(1);
  });

  it("dismissCard removes from any bucket", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.appendCard(mkCard("b", "verified"));
    s.dismissCard("a");
    s.dismissCard("b");
    const st = useCardsStore.getState();
    expect(st.critical).toEqual([]);
    expect(st.calm).toEqual([]);
  });

  it("applyAction tags the card in critical zone", () => {
    const s = useCardsStore.getState();
    s.appendCard(mkCard("a", "disputed"));
    s.applyAction("a", "dismissed");
    expect(useCardsStore.getState().critical[0]._action).toBe("dismissed");
  });
});
