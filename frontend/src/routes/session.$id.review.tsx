import { useEffect, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useAuth } from "@clerk/clerk-react";

import { CalmZone } from "@/components/calm_zone";
import { CriticalZone } from "@/components/critical_zone";
import { HelperBanner } from "@/components/helper_banner";
import { HelperInstallPanel } from "@/components/helper_install_panel";
import { RecapBar } from "@/components/recap_bar";
import { ReviewHeader } from "@/components/review_header";
import { ReviewTranscript } from "@/components/review_transcript";
import { api } from "@/lib/api";
import {
  dismissRecap,
  markHelperReady,
  shouldShowRecapCard,
} from "@/lib/helper_prompt";
import { useCardsStore } from "@/stores/cards_store";
import { useSessionStore } from "@/stores/session_store";

export function ReviewRoute() {
  const { id } = useParams({ strict: false }) as { id: string };
  const { getToken } = useAuth();
  const navigate = useNavigate();

  const [sessionName, setSessionName] = useState("Session");
  const [dateLabel, setDateLabel] = useState("");
  const [showRecap, setShowRecap] = useState(false);
  const [showInstallPanel, setShowInstallPanel] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // The cards + session stores are module-level singletons that survive
    // navigation — reset them so a review never inherits live or prior state.
    useCardsStore.getState().reset();
    useSessionStore.getState().reset();

    async function load() {
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        const session = await api.getSession(id, token);
        if (cancelled) return;
        setSessionName(session.name);
        setDateLabel(
          new Date(session.created_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          }),
        );
        const cards = await api.getSessionCards(id, token);
        if (cancelled) return;
        for (const c of cards) useCardsStore.getState().appendCard(c);
        const lines = await api.getSessionTranscript(id, token);
        if (cancelled) return;
        for (const l of lines) {
          useSessionStore.getState().appendLine({
            id: l.id,
            text: l.text,
            start_ms: l.start_ms,
            end_ms: l.end_ms,
            speaker_label: l.speaker ?? "—",
          });
        }
      } catch (err) {
        console.warn("review load failed", err);
      }
    }

    void load();
    setShowRecap(shouldShowRecapCard());

    return () => {
      cancelled = true;
    };
  }, [id, getToken]);

  return (
    <div className="min-h-screen flex flex-col">
      <ReviewHeader
        sessionName={sessionName}
        dateLabel={dateLabel}
        onNewSession={() => navigate({ to: "/" })}
        onHistory={() => navigate({ to: "/" })}
      />
      <RecapBar />
      {showRecap && (
        <HelperBanner
          headline="More than one voice just now?"
          body={
            <>
              Glass labeled all of that as you. Add the Mac helper and every
              card shows who actually said it.{" "}
              <span className="text-slate-500">Free · tiny download · macOS</span>
            </>
          }
          dismissLabel="Dismiss"
          onGetHelper={() => setShowInstallPanel(true)}
          onDismiss={() => {
            dismissRecap();
            setShowRecap(false);
          }}
        />
      )}
      <main className="relative z-10 grid grid-cols-[1.42fr_8px_1fr] gap-0 px-5 pt-5 pb-2">
        <CriticalZone sessionId={id} ended={true} />
        <div
          className="w-px"
          style={{
            background:
              "linear-gradient(180deg, transparent 0%, rgba(255,255,255,0.06) 12%, rgba(255,255,255,0.06) 88%, transparent 100%)",
          }}
        />
        <CalmZone />
      </main>
      <ReviewTranscript />
      {showInstallPanel && (
        <HelperInstallPanel
          onInstalled={() => {
            markHelperReady();
            setShowInstallPanel(false);
          }}
          onClose={() => setShowInstallPanel(false)}
        />
      )}
    </div>
  );
}
