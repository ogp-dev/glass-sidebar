import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useAuth } from "@clerk/clerk-react";

import { CalmZone } from "@/components/calm_zone";
import { CriticalZone } from "@/components/critical_zone";
import { HelperBanner } from "@/components/helper_banner";
import { HelperInstallPanel } from "@/components/helper_install_panel";
import { LeaveSessionDialog } from "@/components/leave_session_dialog";
import { TopBar } from "@/components/top_bar";
import { TranscriptStrip } from "@/components/transcript_strip";
import { WhoSaidWhatControl } from "@/components/who_said_what_control";
import { api } from "@/lib/api";
import {
  clearHelperReady,
  isHelperReady,
  launchHelper,
  markHelperReady,
  shouldShowHelperBanner,
} from "@/lib/helper_prompt";
import { startMicCapture, type MicCaptureHandle } from "@/lib/mic_capture";
import { openDashboardSocket, type DashboardEvent } from "@/lib/ws";
import { useAudioStore } from "@/stores/audio_store";
import { useCardsStore } from "@/stores/cards_store";
import { useSessionStore } from "@/stores/session_store";

export function LiveRoute() {
  const { id } = useParams({ strict: false }) as { id: string };
  const setSession = useSessionStore((s) => s.setSession);
  const setPartial = useSessionStore((s) => s.setPartial);
  const appendLine = useSessionStore((s) => s.appendLine);
  const appendCard = useCardsStore((s) => s.appendCard);
  const upsertCard = useCardsStore((s) => s.upsertCard);
  const pinCardLocal = useCardsStore((s) => s.pinCard);
  const setRMS = useAudioStore((s) => s.setRMS);
  const { getToken } = useAuth();
  const navigate = useNavigate();

  const [sessionName, setSessionName] = useState("Session");
  const [startedAt] = useState(Date.now());
  const [elapsedMs, setElapsedMs] = useState(0);
  const [helperConnected, setHelperConnected] = useState(true);
  const [authToken, setAuthToken] = useState("");
  const captureRef = useRef<MicCaptureHandle | null>(null);
  const helperLaunchTimer = useRef<number | null>(null);
  const helperFallbackTimer = useRef<number | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [helperDropped, setHelperDropped] = useState(false);
  const [captureMode, setCaptureMode] = useState<"browser" | "helper">(
    "browser",
  );
  const [paused, setPaused] = useState(false);
  const [showInstallPanel, setShowInstallPanel] = useState(false);
  const [showHelperBanner, setShowHelperBanner] = useState(false);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  useEffect(() => {
    // A new session must start clean. The cards + audio stores are
    // module-level singletons that survive client-side navigation, so without
    // an explicit reset a fresh session inherits the previous session's state.
    setSession(id);
    useCardsStore.getState().reset();
    useAudioStore.getState().reset();
    setShowHelperBanner(shouldShowHelperBanner());
  }, [id, setSession]);

  useEffect(() => {
    const t = setInterval(() => setElapsedMs(Date.now() - startedAt), 1000);
    return () => clearInterval(t);
  }, [startedAt]);

  useEffect(() => {
    if (!helperDropped) return;
    const t = setTimeout(() => setHelperDropped(false), 6000);
    return () => clearTimeout(t);
  }, [helperDropped]);

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        setAuthToken(token);
        // If the helper is known-installed, launch it in the background. The
        // session stays on the browser mic until helper_status confirms.
        if (isHelperReady()) launchHelperAndWatch(token);
        try {
          const session = await api.getSession(id, token);
          setSessionName(session.name);
        } catch {
          // ignore — keep default name
        }
        const cards = await api.getSessionCards(id, token);
        for (const c of cards) appendCard(c);
      } catch (err) {
        console.warn("hydrate cards failed", err);
      }
    }

    void hydrate();

    const close = openDashboardSocket({
      sessionId: id,
      onEvent: (ev: DashboardEvent) => {
        if (ev.kind === "transcript_partial") {
          setPartial({ text: ev.text, speaker_label: ev.speaker_label });
        } else if (ev.kind === "transcript_line") {
          appendLine({
            id: ev.id,
            text: ev.text,
            start_ms: ev.start_ms,
            end_ms: ev.end_ms,
            speaker_label: ev.speaker_label,
          });
        } else if (ev.kind === "card") {
          upsertCard({
            id: ev.id,
            claim_text: ev.claim_text,
            claim_type: ev.claim_type,
            state: ev.state,
            verdict: ev.verdict,
            correction: ev.correction,
            confidence: ev.confidence,
            sources: ev.sources,
            pinned: ev.pinned,
            source: ev.source,
            zone: ev.zone,
            query_echo: ev.query_echo,
            speaker: ev.speaker,
          });
        } else if (ev.kind === "card_updated") {
          pinCardLocal(ev.id, ev.pinned);
        } else if (ev.kind === "rms") {
          setRMS(ev.mic, ev.sys);
        } else if (ev.kind === "helper_status") {
          setHelperConnected(ev.connected);
          if (ev.connected) {
            if (helperLaunchTimer.current) {
              clearTimeout(helperLaunchTimer.current);
              helperLaunchTimer.current = null;
            }
            if (helperFallbackTimer.current) {
              clearTimeout(helperFallbackTimer.current);
              helperFallbackTimer.current = null;
            }
            setCaptureMode("helper");
            setShowHelperBanner(false);
            setHelperDropped(false);
          } else if (!helperFallbackTimer.current) {
            // Helper dropped — give it a short grace period to reconnect
            // (it reconnects itself on audio-device changes); if it doesn't,
            // fall back to the browser mic so the session never loses audio.
            helperFallbackTimer.current = window.setTimeout(() => {
              helperFallbackTimer.current = null;
              setCaptureMode("browser");
              setHelperDropped(true);
            }, 2500);
          }
        }
      },
    });

    return () => {
      cancelled = true;
      close();
      if (helperLaunchTimer.current) clearTimeout(helperLaunchTimer.current);
      if (helperFallbackTimer.current) clearTimeout(helperFallbackTimer.current);
    };
  }, [id, setPartial, appendLine, appendCard, upsertCard, pinCardLocal, setRMS, getToken]);

  useEffect(() => {
    // In helper mode the Mac helper feeds audio; while paused, nothing
    // captures. Either way keep the browser mic off so only one client ever
    // streams to the audio socket.
    if (captureMode !== "browser" || paused) return;

    let handle: MicCaptureHandle | null = null;
    let cancelled = false;

    void startMicCapture({
      sessionId: id,
      onStatus: (status, detail) => {
        if (status === "error") {
          setCaptureError(detail ?? "Audio capture failed");
        } else if (status === "live") {
          setCaptureError(null);
        }
      },
      onRms: (rms) => setRMS(rms, 0),
    })
      .then((h) => {
        if (cancelled) {
          h.stop();
          return;
        }
        handle = h;
        captureRef.current = h;
      })
      .catch(() => {
        // onStatus already surfaced the error to the user
      });

    return () => {
      cancelled = true;
      handle?.stop();
      captureRef.current = null;
    };
  }, [id, setRMS, captureMode, paused]);

  async function handleStop() {
    // Mark the row ended, then navigate to the read-only review screen. The
    // browser-mic effect tears its capture down when this route unmounts.
    const token = authToken || (await getToken()) || "";
    try {
      await api.stopSession(id, token);
    } catch {
      // navigate to the review screen regardless — the session is over
    }
    navigate({ to: "/session/$id/review", params: { id } });
  }

  async function handleLeaveHome() {
    // Leaving via the logo ends the session, exactly like Stop — otherwise the
    // row is orphaned in 'live' state. Then go home rather than to review.
    const token = authToken || (await getToken()) || "";
    try {
      await api.stopSession(id, token);
    } catch {
      // navigate home regardless — the session is over
    }
    navigate({ to: "/" });
  }

  /// Fire the helper launch and watch for it to connect. The session keeps
  /// running on the browser mic; a `helper_status: connected` event upgrades
  /// it. If nothing connects within 10s the helperReady flag was stale —
  /// clear it and surface the install banner.
  function launchHelperAndWatch(token: string) {
    launchHelper(id, token);
    if (helperLaunchTimer.current) clearTimeout(helperLaunchTimer.current);
    helperLaunchTimer.current = window.setTimeout(() => {
      helperLaunchTimer.current = null;
      clearHelperReady();
      setShowHelperBanner(true);
    }, 10_000);
  }

  async function activateHelper() {
    const token = authToken || (await getToken()) || "";
    setCaptureError(null);
    launchHelperAndWatch(token);
  }

  function handleWhoSaidWhat() {
    if (isHelperReady()) {
      void activateHelper();
    } else {
      setShowInstallPanel(true);
    }
  }

  function handleHelperInstalled() {
    markHelperReady();
    setShowInstallPanel(false);
    void activateHelper();
  }

  return (
    <div className="h-screen flex flex-col">
      <TopBar
        sessionId={id}
        sessionName={sessionName}
        elapsedMs={elapsedMs}
        paused={paused}
        onStop={handleStop}
        onHome={() => setShowLeaveConfirm(true)}
        onPauseToggle={
          captureMode === "browser" ? () => setPaused((p) => !p) : undefined
        }
        captureControl={
          <WhoSaidWhatControl
            mode={captureMode}
            helperConnected={helperConnected}
            onActivate={handleWhoSaidWhat}
          />
        }
      />
      {showHelperBanner && captureMode === "browser" && (
        <HelperBanner
          glow
          headline="Recording with someone else?"
          body="Turn on “Who said what” so Glass can tell you apart."
          dismissLabel="Maybe later"
          onGetHelper={() => setShowInstallPanel(true)}
          onDismiss={() => setShowHelperBanner(false)}
        />
      )}
      {captureMode === "browser" && captureError && (
        <div className="relative z-10 mx-5 mt-3 rounded-lg border border-rose-400/30 bg-rose-500/[0.12] px-4 py-2.5 text-[13px] text-rose-200">
          {captureError}. Allow microphone access for this site in your browser,
          then reload the page.
        </div>
      )}
      {helperDropped && captureMode === "browser" && (
        <div className="relative z-10 mx-5 mt-3 rounded-lg border border-amber-400/25 bg-amber-500/[0.10] px-4 py-2.5 text-[13px] text-amber-200">
          Helper disconnected — back on your browser mic. Tap “Who said what”
          to reconnect it.
        </div>
      )}
      <main className="relative z-10 grid grid-cols-[1.42fr_8px_1fr] gap-0 px-5 pt-5 pb-[80px] flex-1 overflow-hidden">
        <CriticalZone sessionId={id} />
        <div
          className="w-px"
          style={{
            background:
              "linear-gradient(180deg, transparent 0%, rgba(255,255,255,0.06) 12%, rgba(255,255,255,0.06) 88%, transparent 100%)",
          }}
        />
        <CalmZone />
      </main>
      <TranscriptStrip />
      {showInstallPanel && (
        <HelperInstallPanel
          onInstalled={handleHelperInstalled}
          onClose={() => setShowInstallPanel(false)}
        />
      )}
      {showLeaveConfirm && (
        <LeaveSessionDialog
          onConfirm={handleLeaveHome}
          onCancel={() => setShowLeaveConfirm(false)}
        />
      )}
    </div>
  );
}
