import { Link } from "@tanstack/react-router";
import { UserButton } from "@clerk/clerk-react";

interface Props {
  sessionName: string;
  dateLabel: string;
  onNewSession: () => void;
  onHistory: () => void;
}

/// Calm header for the read-only review screen — no live cockpit chrome.
export function ReviewHeader({
  sessionName,
  dateLabel,
  onNewSession,
  onHistory,
}: Props) {
  return (
    <header className="glass-thick relative z-10 h-14 px-5 flex items-center gap-4">
      <Link
        to="/"
        title="Back to home"
        className="flex items-center gap-2.5 rounded-md hover:opacity-80 transition-opacity"
      >
        <div className="relative w-7 h-7 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-sky-400/40 via-violet-500/40 to-rose-400/40" />
          <div className="absolute inset-0 border border-white/10 rounded-lg" />
          <div className="absolute inset-0 flex items-center justify-center">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.9"
            >
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
        </div>
        <span className="text-[13px] font-semibold tracking-tight">
          Glass Sidebar
        </span>
      </Link>

      <div className="ml-3 flex items-center gap-2 px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.06]">
        <span className="text-[11px] font-medium text-slate-300">
          {sessionName}
        </span>
        {dateLabel && (
          <>
            <span className="text-slate-600">·</span>
            <span className="text-[11px] text-slate-500">{dateLabel}</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-400/25">
        <svg
          className="w-3 h-3 text-emerald-300"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
        <span className="text-[11px] font-semibold text-emerald-300 tracking-wide">
          Saved
        </span>
      </div>

      <div className="ml-auto flex items-center gap-4">
        <button
          onClick={onHistory}
          className="press text-[12px] font-medium px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 inline-flex items-center gap-1.5"
        >
          <svg
            className="w-3 h-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3v5h5" />
            <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
            <path d="M12 7v5l4 2" />
          </svg>
          View history
        </button>
        <button
          onClick={onNewSession}
          className="press text-[12px] font-medium px-3 py-1.5 rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 text-white inline-flex items-center gap-1.5"
        >
          <svg
            className="w-3 h-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.6"
            strokeLinecap="round"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New session
        </button>
        <UserButton
          afterSignOutUrl="/"
          appearance={{ elements: { avatarBox: "w-8 h-8" } }}
        />
      </div>
    </header>
  );
}
