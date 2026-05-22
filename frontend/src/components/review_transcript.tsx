import { useSessionStore } from "@/stores/session_store";

/// Read-only transcript section for the review screen. Reads the lines the
/// review route loaded into the session store from GET /sessions/{id}/transcript.
export function ReviewTranscript() {
  const lines = useSessionStore((s) => s.lines);
  if (lines.length === 0) return null;
  return (
    <section className="mx-5 mb-8 mt-2">
      <h3 className="label-xs text-slate-400 mb-2">Transcript</h3>
      <div className="space-y-1.5 glass-thin rounded-xl px-4 py-3">
        {lines.map((l) => (
          <div key={l.id} className="flex gap-3 text-[13px]">
            <span
              className={
                "label-xs w-20 shrink-0 " +
                (l.speaker_label.startsWith("Guest")
                  ? "text-amber-300/80"
                  : "text-slate-500")
              }
            >
              {l.speaker_label}
            </span>
            <span className="text-slate-300">{l.text}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
