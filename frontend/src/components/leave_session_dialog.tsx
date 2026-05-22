interface Props {
  /// End the session and navigate home.
  onConfirm: () => void;
  /// Dismiss the dialog and stay in the live session.
  onCancel: () => void;
}

/// Confirm shown when the user clicks the logo during a live session. Leaving
/// ends the session, so make that explicit before navigating away.
export function LeaveSessionDialog({ onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass-thick w-[400px] rounded-2xl border border-white/10 p-6 space-y-4">
        <h3 className="text-[15px] font-semibold text-slate-100">
          End this session?
        </h3>
        <p className="text-[13px] text-slate-400 leading-relaxed">
          Going home ends the session. Your transcript and fact-cards are saved
          — you can reopen them anytime from Recent sessions.
        </p>
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={onConfirm}
            className="press rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 px-4 py-2 text-[13px] font-semibold text-white"
          >
            End &amp; go home
          </button>
          <button
            onClick={onCancel}
            className="press rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-4 py-2 text-[13px] text-slate-300"
          >
            Keep recording
          </button>
        </div>
      </div>
    </div>
  );
}
