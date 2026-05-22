import type { SessionListItemDTO } from "@/lib/api";

interface Props {
  sessions: SessionListItemDTO[];
  onOpen: (id: string) => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/// The Recent-sessions list on the start page. Each row opens that session's
/// read-only review screen.
export function SessionList({ sessions, onOpen }: Props) {
  if (sessions.length === 0) {
    return <p className="text-[13px] text-slate-500">No sessions yet.</p>;
  }
  return (
    <ul className="space-y-1.5">
      {sessions.map((s) => (
        <li key={s.id}>
          <button
            onClick={() => onOpen(s.id)}
            className="press w-full text-left rounded-md bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] px-3.5 py-2.5 flex items-center gap-3"
          >
            <span className="text-[13px] font-medium text-slate-200 flex-1 truncate">
              {s.name}
            </span>
            <span className="text-[11px] text-slate-500 shrink-0">
              {formatDate(s.created_at)}
            </span>
            <span className="text-[11px] text-slate-500 shrink-0">
              {s.card_count} {s.card_count === 1 ? "card" : "cards"}
              {s.disputed_count > 0 && (
                <span className="text-rose-300"> · {s.disputed_count} disputed</span>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
