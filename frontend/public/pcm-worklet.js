// AudioWorklet processor for browser mic capture.
//
// Runs on the audio render thread. Buffers mono Float32 input from the mic,
// converts it to 16-bit little-endian PCM, and posts ~80ms chunks to the main
// thread. The main thread frames each chunk and streams it to the backend —
// which expects linear16 / 48 kHz, the same format the Mac helper sends.

const TARGET_SAMPLES = 3840; // 80 ms at 48 kHz

class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._chunks = [];
    this._count = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || !input[0]) {
      return true;
    }
    const channel = input[0];
    this._chunks.push(new Float32Array(channel));
    this._count += channel.length;

    if (this._count >= TARGET_SAMPLES) {
      const merged = new Float32Array(this._count);
      let offset = 0;
      for (const c of this._chunks) {
        merged.set(c, offset);
        offset += c.length;
      }
      const pcm = new Int16Array(merged.length);
      for (let i = 0; i < merged.length; i++) {
        const s = Math.max(-1, Math.min(1, merged[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this._chunks = [];
      this._count = 0;
    }
    return true;
  }
}

registerProcessor("pcm-capture", PCMCaptureProcessor);
