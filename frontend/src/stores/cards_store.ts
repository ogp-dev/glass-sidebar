import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import type { CardAction, FactCardDTO } from "@/lib/api";

/// State machine for the two-zone live dashboard (Plan C §1).
///
/// Critical zone: max 3 slots, disputed/partial cards live here. New critical
/// cards displace the oldest non-pinned card that has passed its 20s dwell —
/// if no slot is available, the new card waits in `queuedCritical` until
/// `tickDwell()` (called every 1s by the route) finds an eligible slot.
///
/// Manual cards (source='manual') ALWAYS land in critical with pinned=true,
/// regardless of their resolved state. They occupy a slot like any other
/// critical card; if all slots are filled with pinned cards, manual cards
/// also queue.
///
/// Calm zone: unbounded scrollable list. Verified/heads_up/opinion/unverified
/// cards live here.
///
/// Demoted strip: small chips at bottom of critical zone, FIFO max 5. Click
/// to restore the card to critical with a fresh 20s dwell.

const DWELL_MS = 20_000;
const MAX_CRITICAL = 3;
const MAX_DEMOTED_STRIP = 5;

export type CardWithMeta = FactCardDTO & {
  _action?: CardAction;
  _dwellStartMs: number;
  /// When the claim was detected — from the server's `detected_at` for history
  /// cards, or client arrival time for live WS cards. Drives the "X ago" label.
  _detectedAtMs: number;
};

interface CardsState {
  critical: CardWithMeta[];
  calm: CardWithMeta[];
  demotedStrip: CardWithMeta[];
  queuedCritical: CardWithMeta[];

  appendCard: (card: FactCardDTO) => void;
  pinCard: (id: string, pinned: boolean) => void;
  dismissCard: (id: string) => void;
  restoreFromDemotedStrip: (id: string) => void;
  applyAction: (id: string, action: CardAction) => void;
  tickDwell: () => void;
  reset: () => void;
}

function isCritical(card: FactCardDTO): boolean {
  if (card.source === "manual") return true;
  return card.state === "disputed" || card.state === "partial";
}

function withMeta(card: FactCardDTO): CardWithMeta {
  const now = Date.now();
  const detected = card.detected_at ? Date.parse(card.detected_at) : now;
  return {
    ...card,
    _dwellStartMs: now,
    _detectedAtMs: Number.isNaN(detected) ? now : detected,
  };
}

function findEligibleDemotion(
  critical: CardWithMeta[],
  now: number,
): CardWithMeta | null {
  // critical[] is ordered newest-first (appendCard prepends), so the LAST
  // element is the oldest insertion. We sort by dwellStartMs ascending and
  // tie-break by insertion order: oldest-inserted wins when timestamps match.
  let best: CardWithMeta | null = null;
  for (let i = critical.length - 1; i >= 0; i--) {
    const c = critical[i];
    if (c.pinned) continue;
    if (now - c._dwellStartMs < DWELL_MS) continue;
    if (best === null || c._dwellStartMs < best._dwellStartMs) {
      best = c;
    }
  }
  return best;
}

export const useCardsStore = create<CardsState>()(
  subscribeWithSelector((set, get) => ({
    critical: [],
    calm: [],
    demotedStrip: [],
    queuedCritical: [],

    appendCard: (card) => {
      const st = get();
      if (
        st.critical.some((c) => c.id === card.id) ||
        st.calm.some((c) => c.id === card.id) ||
        st.queuedCritical.some((c) => c.id === card.id) ||
        st.demotedStrip.some((c) => c.id === card.id)
      ) {
        return;
      }

      const m = withMeta(card);

      if (!isCritical(card)) {
        set({ calm: [m, ...st.calm] });
        return;
      }

      if (st.critical.length < MAX_CRITICAL) {
        set({ critical: [m, ...st.critical] });
        return;
      }

      const now = Date.now();
      const oldest = findEligibleDemotion(st.critical, now);
      if (oldest !== null) {
        set({
          critical: [m, ...st.critical.filter((c) => c.id !== oldest.id)],
          demotedStrip: [oldest, ...st.demotedStrip].slice(0, MAX_DEMOTED_STRIP),
        });
      } else {
        set({ queuedCritical: [...st.queuedCritical, m] });
      }
    },

    pinCard: (id, pinned) =>
      set((s) => ({
        critical: s.critical.map((c) => (c.id === id ? { ...c, pinned } : c)),
        calm: s.calm.map((c) => (c.id === id ? { ...c, pinned } : c)),
      })),

    dismissCard: (id) =>
      set((s) => ({
        critical: s.critical.filter((c) => c.id !== id),
        calm: s.calm.filter((c) => c.id !== id),
        queuedCritical: s.queuedCritical.filter((c) => c.id !== id),
        demotedStrip: s.demotedStrip.filter((c) => c.id !== id),
      })),

    restoreFromDemotedStrip: (id) => {
      const st = get();
      const card = st.demotedStrip.find((c) => c.id === id);
      if (!card) return;
      const restored: CardWithMeta = { ...card, _dwellStartMs: Date.now() };
      const stripWithout = st.demotedStrip.filter((c) => c.id !== id);

      if (st.critical.length < MAX_CRITICAL) {
        set({
          critical: [restored, ...st.critical],
          demotedStrip: stripWithout,
        });
        return;
      }

      const now = Date.now();
      const oldest = findEligibleDemotion(st.critical, now);
      if (oldest === null) {
        set({
          queuedCritical: [...st.queuedCritical, restored],
          demotedStrip: stripWithout,
        });
        return;
      }

      set({
        critical: [restored, ...st.critical.filter((c) => c.id !== oldest.id)],
        demotedStrip: [oldest, ...stripWithout].slice(0, MAX_DEMOTED_STRIP),
      });
    },

    applyAction: (id, action) =>
      set((s) => ({
        critical: s.critical.map((c) =>
          c.id === id ? { ...c, _action: action } : c,
        ),
        calm: s.calm.map((c) =>
          c.id === id ? { ...c, _action: action } : c,
        ),
      })),

    tickDwell: () => {
      const st = get();
      if (st.queuedCritical.length === 0) return;

      if (st.critical.length < MAX_CRITICAL) {
        const [head, ...tail] = st.queuedCritical;
        set({
          critical: [{ ...head, _dwellStartMs: Date.now() }, ...st.critical],
          queuedCritical: tail,
        });
        return;
      }

      const now = Date.now();
      const oldest = findEligibleDemotion(st.critical, now);
      if (oldest === null) return;

      const [head, ...tail] = st.queuedCritical;
      set({
        critical: [
          { ...head, _dwellStartMs: now },
          ...st.critical.filter((c) => c.id !== oldest.id),
        ],
        queuedCritical: tail,
        demotedStrip: [oldest, ...st.demotedStrip].slice(0, MAX_DEMOTED_STRIP),
      });
    },

    reset: () =>
      set({
        critical: [],
        calm: [],
        demotedStrip: [],
        queuedCritical: [],
      }),
  })),
);
