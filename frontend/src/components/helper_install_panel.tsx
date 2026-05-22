import { useState, type ReactNode } from "react";

import { HELPER_DOWNLOAD_URL } from "@/lib/helper_prompt";

interface Props {
  /// Called when the user confirms "I've installed it".
  onInstalled: () => void;
  /// Called on "Maybe later" / "Close".
  onClose: () => void;
}

interface Step {
  n: string;
  img: string;
  title: string;
  caption: ReactNode;
}

/// The macOS Gatekeeper walkthrough. Glass Sidebar isn't notarized, so the
/// first launch is blocked — all three steps are shown at once (no scroll, no
/// wizard). The correct button is ringed in green on every screenshot because
/// macOS makes the WRONG choice ("Move to Trash") the blue default.
const STEPS: Step[] = [
  {
    n: "1",
    img: "/install/step-1.png",
    title: "First launch is blocked",
    caption: (
      <>
        Click <strong className="text-emerald-300">Done</strong>.
      </>
    ),
  },
  {
    n: "2",
    img: "/install/step-2.png",
    title: "Open System Settings",
    caption: (
      <>
        <strong className="text-slate-200">Privacy &amp; Security</strong>,
        scroll to <strong className="text-slate-200">Security</strong>, click{" "}
        <strong className="text-emerald-300">Open Anyway</strong>.
      </>
    ),
  },
  {
    n: "3",
    img: "/install/step-3.png",
    title: "Confirm",
    caption: (
      <>
        Click <strong className="text-emerald-300">Open Anyway</strong> once
        more.
      </>
    ),
  },
];

/// Modal overlay surfaced when the user taps "Who said what" without the helper
/// installed (and from the recap card's "Get the helper"). Offer → install steps.
export function HelperInstallPanel({ onInstalled, onClose }: Props) {
  const [stage, setStage] = useState<"offer" | "steps">("offer");

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className={`glass-thick rounded-2xl border border-white/10 p-7 space-y-5 ${
          stage === "offer" ? "w-[420px]" : "w-[min(800px,94vw)]"
        }`}
      >
        {stage === "offer" ? (
          <>
            <h3 className="text-[15px] font-semibold text-slate-100">
              See who said what
            </h3>
            <p className="text-[13px] text-slate-400 leading-relaxed">
              Your browser mic already picks up everyone — but Glass labels
              every voice as you. The Mac helper splits the audio so each
              fact-check shows who actually said it.
            </p>
            <div className="flex items-center gap-2 pt-1">
              <a
                href={HELPER_DOWNLOAD_URL}
                download
                onClick={() => setStage("steps")}
                className="press rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 px-4 py-2 text-[13px] font-semibold text-white"
              >
                Download helper
              </a>
              <button
                onClick={onClose}
                className="press rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-4 py-2 text-[13px] text-slate-300"
              >
                Maybe later
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              Free · tiny download · macOS
            </p>
          </>
        ) : (
          <>
            <div className="space-y-1">
              <h3 className="text-[15px] font-semibold text-slate-100">
                Finish installing — 3 quick steps
              </h3>
              <p className="text-[13px] text-slate-400 leading-relaxed">
                Open the downloaded file and drag{" "}
                <strong className="text-slate-200">Glass Sidebar</strong> into
                your <strong className="text-slate-200">Applications</strong>{" "}
                folder. The first time you open it, macOS walks you through the
                rest — just click the{" "}
                <strong className="text-emerald-300">green</strong> button each
                time:
              </p>
            </div>

            <div className="flex items-start justify-center gap-4 overflow-x-auto">
              {STEPS.map((s) => (
                <div
                  key={s.n}
                  className="flex shrink-0 flex-col items-center gap-2.5"
                >
                  <div className="flex items-center gap-2 self-start">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-sky-500 text-[11px] font-bold text-white">
                      {s.n}
                    </span>
                    <span className="text-[12px] font-semibold text-slate-200">
                      {s.title}
                    </span>
                  </div>
                  <img
                    src={s.img}
                    alt={s.title}
                    className="h-[210px] w-auto rounded-lg border border-white/10"
                  />
                  <p className="max-w-[300px] text-center text-[12px] leading-relaxed text-slate-400">
                    {s.caption}
                  </p>
                </div>
              ))}
            </div>

            <div className="space-y-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-[12px] leading-relaxed text-slate-400">
              <p>
                <strong className="text-slate-200">
                  Ignore the blue button.
                </strong>{" "}
                macOS makes <em>Move to Trash</em> the default — always click
                the button ringed in{" "}
                <strong className="text-emerald-300">green</strong> instead.
                That&rsquo;s normal for apps outside the App Store, and safe.
              </p>
              <p>
                When Glass Sidebar opens, allow{" "}
                <strong className="text-slate-200">Screen Recording</strong> and{" "}
                <strong className="text-slate-200">Microphone</strong> — then it
                joins every session on its own.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={onInstalled}
                className="press rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 px-4 py-2 text-[13px] font-semibold text-white"
              >
                I&rsquo;ve installed it
              </button>
              <button
                onClick={onClose}
                className="press rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] px-4 py-2 text-[13px] text-slate-300"
              >
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
