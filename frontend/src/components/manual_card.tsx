import { useState } from "react";
import { useAuth } from "@clerk/clerk-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatAgo } from "@/lib/time";
import { useCardsStore, type CardWithMeta } from "@/stores/cards_store";

interface Props {
  card: CardWithMeta;
  sessionId: string;
  now: number;
}

const STATE_BADGE: Record<
  string,
  { label: string; bg: string; border: string; text: string }
> = {
  verified: {
    label: "Verified",
    bg: "bg-emerald-400/15",
    border: "border-emerald-400/30",
    text: "text-emerald-200",
  },
  disputed: {
    label: "Disputed",
    bg: "bg-rose-400/15",
    border: "border-rose-400/30",
    text: "text-rose-200",
  },
  partial: {
    label: "Partial",
    bg: "bg-amber-400/15",
    border: "border-amber-400/30",
    text: "text-amber-200",
  },
  unverified: {
    label: "Unverified",
    bg: "bg-slate-400/15",
    border: "border-slate-400/30",
    text: "text-slate-200",
  },
  opinion: {
    label: "Opinion",
    bg: "bg-violet-400/15",
    border: "border-violet-400/30",
    text: "text-violet-200",
  },
  heads_up: {
    label: "Heads-up",
    bg: "bg-sky-400/15",
    border: "border-sky-400/30",
    text: "text-sky-200",
  },
  pending: {
    label: "Pending",
    bg: "bg-slate-400/15",
    border: "border-slate-400/30",
    text: "text-slate-300",
  },
};

export function ManualCard({ card, sessionId, now }: Props) {
  const pinCardLocal = useCardsStore((s) => s.pinCard);
  const dismissLocal = useCardsStore((s) => s.dismissCard);
  const badge = STATE_BADGE[card.state] ?? STATE_BADGE.unverified;
  const { getToken } = useAuth();
  const [busyPin, setBusyPin] = useState(false);

  async function togglePin() {
    setBusyPin(true);
    pinCardLocal(card.id, !card.pinned);
    try {
      const token = await getToken();
      if (!token) return;
      await api.pinCard(sessionId, card.id, !card.pinned, token);
    } finally {
      setBusyPin(false);
    }
  }

  return (
    <article className="glass-medium glow-manual arrive lift relative rounded-2xl p-4 flex flex-col gap-2.5">
      <header className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-violet-500/20 border border-violet-400/40 flex items-center justify-center">
          <svg
            className="w-3 h-3 text-violet-200"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
          >
            <path d="M12 2l3 7h7l-5.5 4 2 7L12 16l-6.5 4 2-7L2 9h7l3-7z" />
          </svg>
        </div>
        <span className="label-xs text-violet-200">Manual</span>
        <span className="text-[10px] text-slate-500">you asked</span>
        <span
          className={cn(
            "ml-2 px-1.5 py-[1px] rounded text-[9px] uppercase tracking-wider font-bold border",
            badge.bg,
            badge.border,
            badge.text,
          )}
        >
          {badge.label}
        </span>

        <div className="ml-auto flex items-center gap-0.5">
          <span className="text-[10px] text-slate-500 tnum mr-1">
            {formatAgo(now - card._detectedAtMs)}
          </span>
          <button
            onClick={togglePin}
            disabled={busyPin}
            className={cn(
              "press p-1 rounded-md hover:bg-white/[0.06]",
              card.pinned ? "text-amber-300" : "text-slate-400",
            )}
            title={card.pinned ? "Unpin" : "Pin to keep"}
          >
            <svg
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill={card.pinned ? "currentColor" : "none"}
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 17v5" />
              <path d="M9 10.76V3h6v7.76l3 5.24H6l3-5.24z" />
            </svg>
          </button>
          <button
            onClick={() => dismissLocal(card.id)}
            className="press p-1 rounded-md hover:bg-white/[0.06]"
            title="Dismiss"
          >
            <svg
              className="w-3.5 h-3.5 text-slate-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </header>

      {card.query_echo && (
        <p
          className="text-[14px] leading-[1.4] text-violet-200/80 italic"
          style={{ letterSpacing: "-0.01em" }}
        >
          ▸ "{card.query_echo}"
        </p>
      )}

      <p
        className="text-[19px] leading-[1.32] text-slate-50 font-semibold"
        style={{ letterSpacing: "-0.018em" }}
      >
        {card.verdict ?? card.claim_text}
      </p>

      {card.correction && (
        <div className="rounded-lg bg-gradient-to-br from-amber-400/[0.08] to-amber-300/[0.04] border border-amber-400/20 px-3 py-2.5">
          <div className="flex items-baseline gap-2">
            <span className="label-xs text-amber-300/90 shrink-0">Fix</span>
            <p
              className="text-[15px] leading-[1.35] text-amber-50/95 font-medium"
              style={{ letterSpacing: "-0.012em" }}
            >
              {card.correction}
            </p>
          </div>
        </div>
      )}

      {card.sources.length > 0 && (
        <div className="flex items-center gap-1.5 pt-0.5 flex-wrap">
          {card.sources.slice(0, 4).map((s, i) => (
            <a
              key={i}
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="press inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] text-slate-300 hover:text-white hover:bg-white/[0.04]"
            >
              <span className="src-dot !w-2 !h-2 bg-slate-500" />
              <span>{s.publisher ?? "Source"}</span>
            </a>
          ))}
        </div>
      )}
    </article>
  );
}
