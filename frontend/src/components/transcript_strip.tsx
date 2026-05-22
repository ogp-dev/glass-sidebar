import { useState } from "react";

import { useSessionStore } from "@/stores/session_store";

export function TranscriptStrip() {
  const partial = useSessionStore((s) => s.partial);
  const lines = useSessionStore((s) => s.lines);
  const [expanded, setExpanded] = useState(false);

  const latest = lines[lines.length - 1];
  const display = partial?.text ?? latest?.text ?? "Waiting for speech…";
  const speaker = partial?.speaker_label ?? latest?.speaker_label ?? "—";
  // Guest audio comes from a separate stream — colour-code it so the host can
  // tell at a glance whether they or the guest is on record.
  const isGuest = speaker.startsWith("Guest");

  return (
    <>
      <footer className="glass-thin fixed bottom-0 inset-x-0 z-20 h-12 flex items-center px-5 gap-4">
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center gap-1.5">
            <div
              className={
                "w-1.5 h-1.5 rounded-full " +
                (isGuest ? "bg-amber-400" : "bg-sky-400")
              }
            />
            <span
              className={
                "label-xs " + (isGuest ? "text-amber-300" : "text-slate-400")
              }
            >
              {speaker}
            </span>
          </div>
        </div>
        <div className="flex-1 overflow-hidden ticker-fade">
          <p className="text-[13px] text-slate-300 whitespace-nowrap leading-snug">
            {display}
            {partial && <span className="caret" />}
          </p>
        </div>
        <button
          onClick={() => setExpanded((x) => !x)}
          className="press text-[11px] text-slate-400 hover:text-slate-100 px-2.5 py-1 rounded-md hover:bg-white/[0.05] inline-flex items-center gap-1.5"
        >
          {expanded ? "Close" : "History"}
        </button>
      </footer>

      {expanded && (
        <div className="fixed inset-x-0 bottom-12 z-30 max-h-[60vh] overflow-y-auto glass-thick px-5 py-4">
          <div className="space-y-1.5">
            {lines.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No transcript yet.</p>
            ) : (
              lines.map((l) => (
                <div key={l.id} className="flex gap-3 text-[13px]">
                  <span
                    className={
                      "label-xs w-20 shrink-0 tnum " +
                      (l.speaker_label.startsWith("Guest")
                        ? "text-amber-300/80"
                        : "text-slate-500")
                    }
                  >
                    {l.speaker_label}
                  </span>
                  <span className="text-slate-300">{l.text}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </>
  );
}
