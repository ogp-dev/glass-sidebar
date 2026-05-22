import { useState } from "react";

import { cn } from "@/lib/cn";
import { useCardsStore } from "@/stores/cards_store";
import { CalmCard } from "./calm_card";

type Filter = "all" | "verified" | "heads_up" | "opinion";

export function CalmZone() {
  const calm = useCardsStore((s) => s.calm);
  const [filter, setFilter] = useState<Filter>("all");

  const counts = {
    verified: calm.filter((c) => c.state === "verified").length,
    heads_up: calm.filter((c) => c.state === "heads_up").length,
    opinion: calm.filter((c) => c.state === "opinion").length,
  };

  const filtered = filter === "all" ? calm : calm.filter((c) => c.state === filter);

  return (
    <aside className="flex flex-col gap-3 overflow-hidden pl-5 h-full">
      <div className="flex items-center gap-3 px-1">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
        <span className="label-xs text-slate-400">Calm · for reference</span>
        <div className="flex-1 h-px bg-gradient-to-r from-slate-500/15 to-transparent" />
        <span className="text-[10px] text-slate-500 tnum font-medium">
          {calm.length} items
        </span>
      </div>

      <div className="flex items-center gap-1 px-1">
        {(["all", "verified", "heads_up", "opinion"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={cn(
              "press text-[11px] px-2.5 py-1 rounded-md",
              filter === k
                ? "bg-white/[0.06] border border-white/[0.08] text-slate-200"
                : "hover:bg-white/[0.04] text-slate-400 border border-transparent",
            )}
          >
            {k === "all"
              ? "All"
              : k === "heads_up"
                ? "Heads-up"
                : k.charAt(0).toUpperCase() + k.slice(1)}
            {k !== "all" && (
              <span className="tnum text-slate-600 ml-1">{counts[k]}</span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto pr-1 flex flex-col gap-2.5">
        {filtered.length === 0 ? (
          <p className="text-sm text-slate-500 italic px-1">Nothing yet…</p>
        ) : (
          filtered.map((c) => <CalmCard key={c.id} card={c} />)
        )}
      </div>
    </aside>
  );
}
