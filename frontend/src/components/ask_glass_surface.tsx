import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/clerk-react";

import { api } from "@/lib/api";

interface Props {
  sessionId: string;
}

/// Ask Glass — manual verification surface invoked from the top bar or via
/// Cmd+K (Ctrl+K on Linux/Win). Three trigger modes:
///   - free-text query → Sonnet extracts proposition + research + verify
///   - "Verify last claim" → re-runs the most recent claim, bypassing cache
///   - "Re-scan last 30s" → force-detects claims in recent transcript
/// All produce manual+pinned cards in the critical zone (Plan C §3).
export function AskGlassSurface({ sessionId }: Props) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { getToken } = useAuth();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [open]);

  async function dispatch(
    body: { query: string } | { action: "verify_last" | "rescan_30s" },
  ) {
    setSubmitting(true);
    try {
      const token = await getToken();
      if (!token) return;
      await api.ask(sessionId, body, token);
      setValue("");
      setOpen(false);
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="press group relative flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full bg-gradient-to-r from-violet-500/10 to-sky-500/10 hover:from-violet-500/20 hover:to-sky-500/20 border border-violet-400/20 hover:border-violet-400/40 transition"
        aria-label="Ask Glass"
      >
        <span className="relative flex items-center justify-center w-4 h-4 rounded bg-violet-500/30 border border-violet-300/40">
          <svg
            className="w-2.5 h-2.5 text-violet-100"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
          >
            <path d="M12 2l3 7h7l-5.5 4 2 7L12 16l-6.5 4 2-7L2 9h7l3-7z" />
          </svg>
        </span>
        <span className="text-[11.5px] font-medium text-violet-100">Ask Glass</span>
        <kbd className="ml-1 text-[10px] tnum text-violet-200/70 bg-white/[0.06] border border-white/[0.10] rounded px-1 py-0.5 font-medium">
          ⌘K
        </kbd>
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) {
            void dispatch({ query: value.trim() });
          }
        }}
        placeholder="Ask anything or re-verify…"
        className="px-3 py-1.5 w-64 rounded-full bg-white/[0.06] border border-violet-400/40 text-[12.5px] text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-300/60"
        disabled={submitting}
      />
      <button
        onClick={() => void dispatch({ action: "verify_last" })}
        disabled={submitting}
        className="press text-[11px] px-2 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 border border-violet-400/25 text-violet-200 disabled:opacity-50"
      >
        ▸ Verify last
      </button>
      <button
        onClick={() => void dispatch({ action: "rescan_30s" })}
        disabled={submitting}
        className="press text-[11px] px-2 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 border border-violet-400/25 text-violet-200 disabled:opacity-50"
      >
        ▸ Re-scan 30s
      </button>
      <button
        onClick={() => setOpen(false)}
        className="press text-[11px] text-slate-400 px-1 hover:text-slate-200"
      >
        Esc
      </button>
    </div>
  );
}
