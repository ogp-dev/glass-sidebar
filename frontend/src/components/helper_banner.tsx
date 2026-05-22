import { type ReactNode } from "react";

interface Props {
  headline: string;
  body: ReactNode;
  /// Label for the secondary (dismiss) button — e.g. "Dismiss" or "Maybe later".
  dismissLabel: string;
  /// When true, the banner does three faint brand pulses on mount.
  glow?: boolean;
  onGetHelper: () => void;
  onDismiss: () => void;
}

/// Helper-prompt banner — used in-session (live screen) and on the post-session
/// review screen. Same design; the copy and dismiss label differ by context.
export function HelperBanner({
  headline,
  body,
  dismissLabel,
  glow = false,
  onGetHelper,
  onDismiss,
}: Props) {
  return (
    <div
      className={`relative z-[5] mx-5 mt-3 glass-medium rounded-xl px-4 py-3 flex items-center gap-3 border border-white/[0.08]${
        glow ? " helper-glow" : ""
      }`}
    >
      <div className="flex-1">
        <p className="text-[13px] font-medium text-slate-100">{headline}</p>
        <p className="text-[12px] text-slate-400 mt-0.5">{body}</p>
      </div>
      <button
        onClick={onGetHelper}
        className="press shrink-0 rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 px-3.5 py-1.5 text-[12px] font-semibold text-white"
      >
        Get the helper
      </button>
      <button
        onClick={onDismiss}
        className="press shrink-0 text-[12px] text-slate-400 px-2.5 py-1.5 rounded-md hover:bg-white/[0.05]"
      >
        {dismissLabel}
      </button>
    </div>
  );
}
