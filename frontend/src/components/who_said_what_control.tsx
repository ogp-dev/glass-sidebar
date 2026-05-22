interface Props {
  mode: "browser" | "helper";
  helperConnected: boolean;
  onActivate: () => void;
}

/// Top-bar capture-mode control. Browser mode shows a button that offers the
/// helper; helper mode shows a non-interactive status chip (the control is
/// one-way within a session — see the spec).
export function WhoSaidWhatControl({
  mode,
  helperConnected,
  onActivate,
}: Props) {
  if (mode === "helper") {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-violet-500/[0.12] border border-violet-400/25">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            helperConnected ? "bg-violet-300" : "bg-amber-300"
          }`}
        />
        <span className="text-[11px] font-medium text-violet-200">
          Who said what · {helperConnected ? "on" : "starting…"}
        </span>
      </div>
    );
  }
  return (
    <button
      onClick={onActivate}
      title="Tell speakers apart with the Mac helper"
      className="press flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-300"
    >
      <svg
        className="w-3.5 h-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M9 18V5l12-2v13" />
        <circle cx="6" cy="18" r="3" />
        <circle cx="18" cy="16" r="3" />
      </svg>
      <span className="text-[11px] font-medium">Who said what</span>
    </button>
  );
}
