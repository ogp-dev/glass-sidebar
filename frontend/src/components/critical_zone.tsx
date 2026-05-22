import { useEffect, useState } from "react";

import { useCardsStore } from "@/stores/cards_store";
import { CriticalCard } from "./critical_card";
import { ManualCard } from "./manual_card";

interface Props {
  sessionId: string;
  ended?: boolean;
}

export function CriticalZone({ sessionId, ended = false }: Props) {
  const critical = useCardsStore((s) => s.critical);
  const demoted = useCardsStore((s) => s.demotedStrip);
  const queued = useCardsStore((s) => s.queuedCritical);
  const restore = useCardsStore((s) => s.restoreFromDemotedStrip);
  const tick = useCardsStore((s) => s.tickDwell);

  // Drives the per-card "X ago" labels. Frozen once the session ends.
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    // Once the session has ended the review screen is frozen — stop the dwell
    // tick so queued cards don't keep auto-shuffling while the host reads, and
    // freeze the "X ago" clock.
    if (ended) return;
    const id = setInterval(() => {
      setNow(Date.now());
      tick();
    }, 1000);
    return () => clearInterval(id);
  }, [tick, ended]);

  const emptySlots = Math.max(0, 3 - critical.length);

  return (
    <section className="flex flex-col gap-3.5 overflow-hidden pr-5 h-full">
      <div className="flex items-center gap-3 px-1">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
          <span className="label-xs text-rose-300/90">Critical · needs reaction</span>
        </div>
        <div className="flex-1 h-px bg-gradient-to-r from-rose-400/25 via-rose-400/10 to-transparent" />
        <span className="text-[10px] text-slate-500 tnum font-medium">
          {critical.length} / 3 slots
        </span>
        {queued.length > 0 && (
          <span className="text-[10px] text-amber-300 tnum font-medium ml-1">
            {queued.length} waiting
          </span>
        )}
      </div>

      {critical.map((card, i) =>
        card.source === "manual" ? (
          <ManualCard
            key={card.id}
            card={card}
            sessionId={sessionId}
            now={now}
          />
        ) : (
          <CriticalCard
            key={card.id}
            card={card}
            sessionId={sessionId}
            now={now}
            breathing={i === 0 && card.state === "disputed"}
          />
        ),
      )}

      {Array.from({ length: emptySlots }).map((_, i) => (
        <article
          key={`empty-${i}`}
          className="rounded-2xl border border-dashed border-white/[0.08] p-5 text-center flex items-center justify-center min-h-[88px] opacity-60"
        >
          <span className="label-xs text-slate-600">
            Slot {critical.length + i + 1} · open
          </span>
        </article>
      ))}

      <div className="flex-1 min-h-0" />

      {demoted.length > 0 && (
        <>
          <div className="flex items-center gap-2 px-1 mt-2">
            <span className="label-xs text-slate-500">recently demoted</span>
            <div className="flex-1 h-px bg-white/[0.05]" />
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
            {demoted.map((c) => (
              <button
                key={c.id}
                onClick={() => restore(c.id)}
                className="press shrink-0 flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.05] text-[11px] text-slate-400 hover:text-slate-100 transition"
                title="Click to restore"
              >
                <span className="truncate max-w-[160px]">"{c.claim_text}"</span>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
