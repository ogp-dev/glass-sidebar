import { cn } from "@/lib/cn";
import type { CardWithMeta } from "@/stores/cards_store";
import { SpeakerBadge } from "./speaker_badge";

interface Props {
  card: CardWithMeta;
}

const META: Record<
  string,
  {
    label: string;
    glow: string;
    iconBg: string;
    iconColor: string;
    labelColor: string;
  }
> = {
  verified: {
    label: "Verified",
    glow: "glow-verified",
    iconBg: "bg-emerald-500/15 border-emerald-400/25",
    iconColor: "text-emerald-300",
    labelColor: "text-emerald-300",
  },
  heads_up: {
    label: "Heads-up",
    glow: "glow-headsup",
    iconBg: "bg-sky-500/15 border-sky-400/25",
    iconColor: "text-sky-300",
    labelColor: "text-sky-300",
  },
  opinion: {
    label: "Opinion",
    glow: "glow-opinion",
    iconBg: "bg-violet-500/15 border-violet-400/25",
    iconColor: "text-violet-300",
    labelColor: "text-violet-300",
  },
  unverified: {
    label: "Couldn't verify",
    glow: "glow-unverified",
    iconBg: "bg-slate-500/15 border-slate-400/15",
    iconColor: "text-slate-400",
    labelColor: "text-slate-400",
  },
};

export function CalmCard({ card }: Props) {
  const m = META[card.state] ?? META.unverified;
  return (
    <article
      className={cn(
        "glass-light arrive lift relative rounded-xl p-3.5",
        m.glow,
        card.state === "unverified" && "opacity-75",
      )}
    >
      <header className="flex items-center gap-2 mb-2">
        <div
          className={cn(
            "w-5 h-5 rounded-md border flex items-center justify-center",
            m.iconBg,
          )}
        >
          <svg
            className={cn("w-3 h-3", m.iconColor)}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {card.state === "verified" ? (
              <polyline points="20 6 9 17 4 12" />
            ) : card.state === "heads_up" ? (
              <path d="M12 2l3 7h7l-5.5 4 2 7L12 16l-6.5 4 2-7L2 9h7l3-7z" />
            ) : card.state === "opinion" ? (
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            ) : (
              <>
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </>
            )}
          </svg>
        </div>
        <span className={cn("label-xs", m.labelColor)}>{m.label}</span>
        <SpeakerBadge speaker={card.speaker} />
        {card.confidence != null && (
          <span className="text-[10px] text-slate-500 ml-auto tnum">
            conf {card.confidence}
          </span>
        )}
      </header>
      <p
        className="text-[14.5px] leading-[1.4] text-slate-100 font-medium"
        style={{ letterSpacing: "-0.012em" }}
      >
        {card.claim_text}
      </p>
      {card.verdict && card.state === "heads_up" && (
        <p className="mt-1.5 text-[12.5px] leading-[1.4] text-slate-300">
          {card.verdict}
        </p>
      )}
    </article>
  );
}
