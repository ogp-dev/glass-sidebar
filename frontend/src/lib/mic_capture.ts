import { env } from "@/env";

/// Captures the host's microphone in the browser and streams it to the backend
/// audio socket as [0x01][linear16 PCM] frames — the exact protocol the Mac
/// helper speaks (channel 0x01 = host), so the backend needs no special path.
/// This is what makes host fact-checking work with zero install.

const CHANNEL_HOST = 0x01;
const SAMPLE_RATE = 48_000;

export type CaptureStatus =
  | "requesting-mic"
  | "connecting"
  | "live"
  | "stopped"
  | "error";

export interface MicCaptureHandle {
  stop: () => void;
}

function audioWsUrl(sessionId: string): string {
  if (env.wsBase) {
    return `${env.wsBase.replace(/\/+$/, "")}/ws/audio/${sessionId}`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/audio/${sessionId}`;
}

function rmsOfInt16(buf: ArrayBuffer): number {
  const pcm = new Int16Array(buf);
  if (pcm.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < pcm.length; i++) {
    const s = pcm[i] / 0x8000;
    sum += s * s;
  }
  return Math.sqrt(sum / pcm.length);
}

export async function startMicCapture(opts: {
  sessionId: string;
  onStatus: (status: CaptureStatus, detail?: string) => void;
  onRms?: (rms: number) => void;
}): Promise<MicCaptureHandle> {
  const { sessionId, onStatus, onRms } = opts;

  onStatus("requesting-mic");
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
  } catch (err) {
    onStatus("error", "Microphone access was denied");
    throw err;
  }

  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
  // Served as a static file from public/ — a real .js URL works in every
  // browser, unlike a Vite-inlined data: URI (which Safari rejects).
  await ctx.audioWorklet.addModule("/pcm-worklet.js");
  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm-capture");
  source.connect(node);

  const ws = new WebSocket(audioWsUrl(sessionId));
  ws.binaryType = "arraybuffer";

  let stopped = false;

  ws.onopen = () => {
    if (!stopped) onStatus("live");
  };
  ws.onerror = () => {
    if (!stopped) onStatus("error", "Audio connection failed");
  };
  ws.onclose = () => {
    if (!stopped) onStatus("stopped");
  };

  node.port.onmessage = (e: MessageEvent) => {
    const pcm = e.data as ArrayBuffer;
    if (ws.readyState === WebSocket.OPEN) {
      const framed = new Uint8Array(pcm.byteLength + 1);
      framed[0] = CHANNEL_HOST;
      framed.set(new Uint8Array(pcm), 1);
      ws.send(framed);
    }
    onRms?.(rmsOfInt16(pcm));
  };

  onStatus("connecting");

  function stop() {
    if (stopped) return;
    stopped = true;
    node.port.onmessage = null;
    try {
      node.disconnect();
      source.disconnect();
    } catch {
      /* graph already torn down */
    }
    for (const track of stream.getTracks()) track.stop();
    void ctx.close();
    ws.close();
    onStatus("stopped");
  }

  return { stop };
}
