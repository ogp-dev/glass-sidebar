import { type ReactNode } from "react";
import { UserButton } from "@clerk/clerk-react";

import { useAudioStore } from "@/stores/audio_store";
import { AskGlassSurface } from "./ask_glass_surface";

interface Props {
  sessionId: string;
  sessionName: string;
  elapsedMs: number;
  paused: boolean;
  onStop: () => void;
  /// Clicking the brand logo — opens the leave-session confirm.
  onHome: () => void;
  /// When provided, a Pause/Resume button is shown. Omitted in helper mode —
  /// the Mac helper is the capture device there and can't be paused from here.
  onPauseToggle?: () => void;
  captureControl?: ReactNode;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

export function TopBar({
  sessionId,
  sessionName,
  elapsedMs,
  paused,
  onStop,
  onHome,
  onPauseToggle,
  captureControl,
}: Props) {
  const rms = useAudioStore((s) => s.combinedRMS);

  return (
    <header className="glass-thick relative z-10 h-14 px-5 flex items-center gap-4">
      {/* Brand — click to leave for home (confirms first; ends the session) */}
      <button
        type="button"
        onClick={onHome}
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
      </button>

      {/* Show pill — session name + elapsed */}
      <div className="ml-3 flex items-center gap-2 px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.06]">
        <span className="text-[11px] font-medium text-slate-300">
          {sessionName}
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-[11px] text-slate-500 tnum">
          {formatElapsed(elapsedMs)} elapsed
        </span>
      </div>

      {/* Ask Glass */}
      <AskGlassSurface sessionId={sessionId} />

      {/* Capture-mode control ("Who said what") */}
      {captureControl}

      {/* Audio activity bar */}
      <div className="w-20 h-[6px] rounded-full bg-white/[0.06] overflow-hidden relative">
        <div
          className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-gradient-to-r from-emerald-400/80 via-sky-400/80 to-rose-400/80"
          style={{
            transform: `scaleX(${paused ? 0 : rms})`,
            transition: "transform 0.08s linear",
          }}
        />
      </div>

      <div className="ml-auto flex items-center gap-4">
        {paused ? (
          /* PAUSED pill */
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-400/25">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="text-[11px] font-semibold text-amber-300 tracking-wide">
              PAUSED
            </span>
            <span className="text-[11px] text-amber-200/70 tnum font-medium">
              {formatElapsed(elapsedMs)}
            </span>
          </div>
        ) : (
          /* LIVE pill */
          <div className="relative flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-400/25">
            <span className="relative flex w-2 h-2">
              <span className="absolute inset-0 rounded-full bg-emerald-400" />
              <span className="live-ring" />
              <span className="live-ring" style={{ animationDelay: "0.8s" }} />
            </span>
            <span className="text-[11px] font-semibold text-emerald-300 tracking-wide">
              LIVE
            </span>
            <span className="text-[11px] text-emerald-200/70 tnum font-medium">
              {formatElapsed(elapsedMs)}
            </span>
          </div>
        )}

        {onPauseToggle && (
          <button
            onClick={onPauseToggle}
            className="press text-[12px] font-medium px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 inline-flex items-center gap-1.5"
          >
            {paused ? (
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            ) : (
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            )}
            {paused ? "Resume" : "Pause"}
          </button>
        )}

        <button
          onClick={onStop}
          className="press text-[12px] font-medium px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-200 inline-flex items-center gap-1.5"
        >
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="1.5" />
          </svg>
          Stop
        </button>

        {/* Overflow menu */}
        <button
          className="press w-8 h-8 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] flex items-center justify-center text-slate-400"
          title="More"
        >
          <svg
            className="w-4 h-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <circle cx="12" cy="12" r="1" />
            <circle cx="19" cy="12" r="1" />
            <circle cx="5" cy="12" r="1" />
          </svg>
        </button>

        {/* Account */}
        <UserButton
          afterSignOutUrl="/"
          appearance={{ elements: { avatarBox: "w-8 h-8" } }}
        />
      </div>
    </header>
  );
}
