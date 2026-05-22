import { useCardsStore } from "@/stores/cards_store";

/// Episode scorecard — renders below the TopBar only after the host hits Stop.
/// Counts fact-check outcomes across every card bucket (Plan C Task: Stop fix,
/// option B). "Checked" is the sum of the four genuine verification verdicts;
/// heads-up and opinion cards are anticipatory/non-verdict so they're excluded.
export function RecapBar() {
  const critical = useCardsStore((s) => s.critical);
  const calm = useCardsStore((s) => s.calm);
  const demoted = useCardsStore((s) => s.demotedStrip);
  const queued = useCardsStore((s) => s.queuedCritical);

  const all = [...critical, ...calm, ...demoted, ...queued];
  const count = (state: string) => all.filter((c) => c.state === state).length;

  const disputed = count("disputed");
  const verified = count("verified");
  const partial = count("partial");
  const unverified = count("unverified");
  const checked = disputed + verified + partial + unverified;

  return (
    <div className="glass-medium relative z-[5] h-9 px-5 flex items-center gap-3 border-t border-white/[0.05]">
      <span className="label-xs text-slate-400">Episode recap</span>
      <div className="flex items-center gap-2.5 text-[11.5px] font-medium tnum">
        <span className="text-slate-100">{checked} checked</span>
        <span className="text-slate-600">·</span>
        <span className="flex items-center gap-1.5 text-rose-300">
          <span className="src-dot !w-2 !h-2 bg-rose-400" />
          {disputed} disputed
        </span>
        <span className="text-slate-600">·</span>
        <span className="flex items-center gap-1.5 text-emerald-300">
          <span className="src-dot !w-2 !h-2 bg-emerald-400" />
          {verified} verified
        </span>
        <span className="text-slate-600">·</span>
        <span className="flex items-center gap-1.5 text-amber-300">
          <span className="src-dot !w-2 !h-2 bg-amber-400" />
          {partial} partial
        </span>
        {unverified > 0 && (
          <>
            <span className="text-slate-600">·</span>
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="src-dot !w-2 !h-2 bg-slate-500" />
              {unverified} unverified
            </span>
          </>
        )}
      </div>
    </div>
  );
}
