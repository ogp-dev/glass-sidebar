import { useEffect, useState } from "react";
import { useAuth } from "@clerk/clerk-react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";

import { SessionList } from "@/components/session_list";
import { api, type SessionListItemDTO } from "@/lib/api";

export function HomeRoute() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [docket, setDocket] = useState("");
  const [anticipationC, setAnticipationC] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionListItemDTO[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        const list = await api.listSessions(token);
        if (!cancelled) setSessions(list);
      } catch {
        // ignore — leave the list empty
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  async function onStart() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("no token");
      const session = await api.createSession(name.trim(), token);
      if (docket.trim() || anticipationC) {
        await api.setupSession(session.id, docket, anticipationC, token);
      }
      navigate({ to: "/session/$id/live", params: { id: session.id } });
    } catch (err) {
      toast.error(`Could not start session: ${(err as Error).message}`);
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl mx-auto pt-16 px-6 space-y-10">
      <div className="space-y-4">
        <h2 className="text-2xl font-semibold tracking-tight">Start a session</h2>
        <p className="text-sm text-slate-400">
          Name your show and start — Glass Sidebar fact-checks live from your
          browser mic, no install needed.
        </p>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Session name — e.g. TWiST E2289"
          disabled={busy}
          className="w-full rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm"
        />
        <div className="space-y-1.5">
          <textarea
            value={docket}
            onChange={(e) => setDocket(e.target.value)}
            placeholder="Docket — optional. Topics, guest names, companies to pre-research…"
            rows={6}
            disabled={busy}
            className="w-full rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm font-mono leading-relaxed"
          />
          <p className="text-xs text-slate-500">
            Optional — skip it and the agent works reactively.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            id="anticipation-c"
            type="checkbox"
            checked={anticipationC}
            onChange={(e) => setAnticipationC(e.target.checked)}
            disabled={busy}
            className="rounded"
          />
          <label htmlFor="anticipation-c" className="text-sm text-slate-300">
            Enable live web pulls during the show
          </label>
        </div>
        <button
          onClick={onStart}
          disabled={busy || !name.trim()}
          className="press w-full py-3 rounded-xl bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 text-white text-[14px] font-semibold transition disabled:opacity-40"
        >
          {busy ? "Starting…" : "Start session →"}
        </button>
      </div>

      <div className="space-y-3">
        <h3 className="label-xs text-slate-400">Recent sessions</h3>
        <SessionList
          sessions={sessions}
          onOpen={(id) =>
            navigate({ to: "/session/$id/review", params: { id } })
          }
        />
      </div>
    </div>
  );
}
