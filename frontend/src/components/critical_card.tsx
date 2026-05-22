import { useState, type ReactNode } from "react";
import { useAuth } from "@clerk/clerk-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatAgo } from "@/lib/time";
import { useCardsStore, type CardWithMeta } from "@/stores/cards_store";
import { SpeakerBadge } from "./speaker_badge";

interface Props {
  card: CardWithMeta;
  sessionId: string;
  now: number;
  breathing?: boolean;
}

/// Matches the contested value in a claim — currency amounts, magnitudes,
/// percentages, and bare numbers / years — so it can be colour-highlighted
/// inline (per the v3 mockup). Single capturing group → usable with split().
const NUMBER_RE =
  /(\$\s?\d[\d.,]*\s?(?:billion|million|trillion|thousand|bn|b|m|k)?|\d[\d.,]*\s?(?:billion|million|trillion|thousand)|\d[\d.,]*\s?%|\b\d[\d.,]*\b)/gi;

function highlightNumbers(text: string, hlClass: string): ReactNode[] {
  return text.split(NUMBER_RE).map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} className={hlClass}>
        {part}
      </span>
    ) : (
      part
    ),
  );
}

const SEVERITY = {
  disputed: {
    label: "Disputed",
    glow: "glow-disputed",
    iconBg: "bg-rose-500/15 border-rose-400/30",
    iconColor: "text-rose-300",
    labelColor: "text-rose-300",
    correctionBg:
      "from-rose-400/[0.08] to-amber-400/[0.05] border-rose-400/20",
  },
  partial: {
    label: "Partial",
    glow: "glow-partial",
    iconBg: "bg-amber-500/15 border-amber-400/30",
    iconColor: "text-amber-300",
    labelColor: "text-amber-300",
    correctionBg:
      "from-amber-400/[0.08] to-amber-300/[0.04] border-amber-400/20",
  },
} as const;

export function CriticalCard({ card, sessionId, now, breathing }: Props) {
  const meta =
    SEVERITY[card.state as keyof typeof SEVERITY] ?? SEVERITY.disputed;
  const pinCardLocal = useCardsStore((s) => s.pinCard);
  const dismissLocal = useCardsStore((s) => s.dismissCard);
  const { getToken } = useAuth();
  const [busyPin, setBusyPin] = useState(false);

  async function togglePin() {
    setBusyPin(true);
    pinCardLocal(card.id, !card.pinned); // optimistic
    try {
      const token = await getToken();
      if (!token) return;
      await api.pinCard(sessionId, card.id, !card.pinned, token);
    } finally {
      setBusyPin(false);
    }
  }

  const hlClass =
    card.state === "partial"
      ? "bg-amber-400/20 px-1.5 rounded text-white"
      : "bg-rose-400/20 px-1.5 rounded text-white";

  return (
    <article
      className={cn(
        "glass-medium arrive lift relative rounded-2xl p-4 flex flex-col gap-2.5",
        meta.glow,
        breathing && "breathe",
      )}
    >
      <header className="flex items-center gap-2">
        <div
          className={cn(
            "w-6 h-6 rounded-md border flex items-center justify-center",
            meta.iconBg,
          )}
        >
          <svg
            className={cn("w-3 h-3", meta.iconColor)}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {card.state === "partial" ? (
              <>
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </>
            ) : (
              <>
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </>
            )}
          </svg>
        </div>
        <span className={cn("label-xs", meta.labelColor)}>{meta.label}</span>
        <SpeakerBadge speaker={card.speaker} />
        {card.confidence != null && (
          <span className="text-[10px] text-slate-500 tnum">conf {card.confidence}</span>
        )}

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

      <p
        className="text-[19px] leading-[1.32] text-slate-50 font-semibold"
        style={{ letterSpacing: "-0.018em" }}
      >
        <span className="text-slate-500 font-normal">"</span>
        {highlightNumbers(card.claim_text, hlClass)}
        <span className="text-slate-500 font-normal">"</span>
      </p>

      {card.correction && (
        <div
          className={cn(
            "rounded-lg bg-gradient-to-br border px-3 py-2.5",
            meta.correctionBg,
          )}
        >
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
          {card.sources.slice(0, 3).map((s, i) => (
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
          {card.sources.length > 3 && (
            <span className="text-[10px] text-slate-500 ml-1">
              +{card.sources.length - 3}
            </span>
          )}
        </div>
      )}
    </article>
  );
}
