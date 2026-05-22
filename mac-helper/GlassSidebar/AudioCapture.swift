import AVFoundation
import Foundation
import ScreenCaptureKit

enum AudioChannel: UInt8 {
    case mic = 0x01
    case system = 0x02
}

enum AudioCaptureError: Error {
    /// The input node reports a 0 Hz / 0-channel format — no usable mic.
    case noInputDevice
}

/// Sink that receives encoded audio frames + auxiliary text frames (RMS, etc).
/// The WebSocketClient conforms to this.
protocol AudioFrameSink: AnyObject {
    func send(channel: AudioChannel, opusFrame: Data)
    func sendText(_ text: String)
}

// Default no-op so legacy sink implementations (if any) keep compiling.
extension AudioFrameSink {
    func sendText(_ text: String) {}
}

/// Captures the host's microphone (via AVAudioEngine) and system audio
/// (via ScreenCaptureKit). Frames are encoded and routed to `sink` with
/// a channel tag so the backend can keep mic and system audio separate.
///
/// Also computes RMS per ~100ms window on both channels and ships it to the
/// backend as a JSON text frame at 10 Hz. The dashboard renders this as the
/// live audio activity bar in the top header.
final class AudioCapture: NSObject {
    weak var sink: AudioFrameSink?

    private let mixSampleRate: Double = 48_000
    private let micEngine = AVAudioEngine()
    private var scStream: SCStream?
    private let encoder = OpusEncoder(sampleRate: 48_000)

    // RMS throttling — emit a JSON text frame at most every 100 ms (10 Hz).
    private let rmsQueue = DispatchQueue(label: "glass.audio.rms")
    private var lastRMSEmittedAt: TimeInterval = 0
    private var lastMicRMS: Float = 0
    private var lastSysRMS: Float = 0
    private var loggedFirstSysBuffer = false

    // Mic resampling. The backend tells Deepgram the stream is 48 kHz, so the
    // helper MUST emit 48 kHz regardless of the input device's native rate —
    // Bluetooth headsets commonly run the mic at 16/24 kHz, and feeding that
    // to Deepgram as 48 kHz garbles every word (2× speed). float32 keeps both
    // computeRMS and OpusEncoder working.
    private let micTargetFormat = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
        sampleRate: 48_000,
        channels: 1,
        interleaved: false
    )!
    private var micConverter: AVAudioConverter?

    // Device-change resilience. A Bluetooth mic appearing/disappearing mid-
    // session posts AVAudioEngineConfigurationChange; AVAudioEngine stops
    // itself before posting, leaving capture dead with a stale input format.
    // We observe it and rebuild the mic graph (new converter, re-tap, restart)
    // on a serial queue, coalescing the 2–3 notifications a switch emits.
    private let micRebuildQueue = DispatchQueue(label: "glass.audio.mic-rebuild")
    private var isCapturing = false
    private var observingConfigChange = false
    private var micTapInstalled = false
    private var rebuildPending = false

    /// v1 captures the **microphone only**. System-audio capture (the guest's
    /// voice via ScreenCaptureKit) is disabled on purpose:
    ///   • the backend discards system-channel frames — only the mic is fed to
    ///     Deepgram in v1, so capturing system audio achieves nothing;
    ///   • touching `SCShareableContent` forces a macOS **Screen Recording**
    ///     permission prompt on every launch (the grant does not persist for
    ///     an ad-hoc-signed app), which is pure friction for zero benefit.
    /// Plan D: the backend now runs a dedicated Deepgram stream for the guest,
    /// so system audio is captured and fact-checked. This brings back the
    /// macOS Screen Recording permission prompt — accepted tradeoff.
    static let enableSystemAudio = true

    /// Start audio capture. The microphone is essential — it carries the host
    /// voice that drives transcription — so a mic failure is fatal and
    /// rethrown. System audio, when enabled, is best-effort.
    func start() async throws {
        HelperLog.write("start: beginning mic capture")
        try startMicCapture()
        HelperLog.write("start: mic capture OK")
        guard Self.enableSystemAudio else {
            HelperLog.write("start: system audio disabled by flag")
            return
        }
        do {
            HelperLog.write("start: requesting screen-recording permission")
            try await requestPermissions()
            HelperLog.write("start: permission probe OK — starting system capture")
            try await startSystemCapture()
            HelperLog.write("start: system capture started OK")
        } catch {
            HelperLog.write("start: SYSTEM AUDIO FAILED: \(error)")
            NSLog(
                "[GlassSidebar] system audio unavailable (non-fatal): %@",
                String(describing: error)
            )
        }
    }

    /// Tear down capture. Awaits the ScreenCaptureKit stop so the next session
    /// can start a fresh SCStream without racing this teardown — the cause of
    /// system audio silently failing on the 2nd session of a process.
    func stop() async {
        isCapturing = false
        // Run the mic teardown on the rebuild queue so it can't race a
        // device-change rebuild already in flight on that queue.
        micRebuildQueue.sync {
            if observingConfigChange {
                NotificationCenter.default.removeObserver(
                    self,
                    name: .AVAudioEngineConfigurationChange,
                    object: micEngine
                )
                observingConfigChange = false
            }
            micEngine.stop()
            if micTapInstalled {
                micEngine.inputNode.removeTap(onBus: 0)
                micTapInstalled = false
            }
        }
        if let stream = scStream {
            try? await stream.stopCapture()
        }
        scStream = nil
        micConverter = nil
    }

    private func requestPermissions() async throws {
        // Touching SCShareableContent triggers the Screen Recording
        // permission prompt on first run. Mic prompt is triggered by
        // AVAudioEngine.start() below. Both prompts pop natively.
        _ = try await SCShareableContent.current
    }

    private func startMicCapture() throws {
        if !observingConfigChange {
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(handleConfigurationChange(_:)),
                name: .AVAudioEngineConfigurationChange,
                object: micEngine
            )
            observingConfigChange = true
        }
        try installMicTapAndStart()
        isCapturing = true
    }

    /// Build the mic capture graph and start the engine. Shared by the initial
    /// start and every rebuild after a device change.
    ///
    /// The tap is installed with `format: nil` — the engine taps the bus in
    /// its *own* current format. Passing an explicit format that disagrees
    /// with the live hardware format makes `installTap` raise an NSException,
    /// an Objective-C exception Swift cannot catch, which aborts the whole
    /// process. During a device change the format read below is briefly out of
    /// sync with the hardware, so we never hand one to the tap — the converter
    /// adapts to the live buffer format instead (see `resampleMic`).
    private func installMicTapAndStart() throws {
        let input = micEngine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        // A device unplugged with nothing to replace it leaves the input node
        // at a 0 Hz / 0-channel format. Bail and let the retry catch the next
        // device rather than tapping a dead node.
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw AudioCaptureError.noInputDevice
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: nil) { [weak self] buffer, _ in
            guard let self = self else { return }
            // Resample to 48 kHz mono FIRST — RMS, encoding and the wire frame
            // all assume the target rate.
            guard let resampled = self.resampleMic(buffer) else { return }
            let rms = AudioCapture.computeRMS(resampled)
            self.rmsQueue.async {
                self.lastMicRMS = rms
                self.maybeEmitRMSLocked()
            }
            if let frame = self.encoder.encode(buffer: resampled) {
                self.sink?.send(channel: .mic, opusFrame: frame)
            }
        }
        micTapInstalled = true
        try micEngine.start()
    }

    /// AVAudioEngineConfigurationChange handler. The engine has already stopped
    /// itself; we rebuild the mic graph. Fires on an arbitrary thread and a
    /// device switch emits it 2–3×, so hop to the serial queue and coalesce.
    @objc private func handleConfigurationChange(_ note: Notification) {
        HelperLog.write("audio: configuration change — mic device changed")
        micRebuildQueue.async { [weak self] in
            guard let self, self.isCapturing, !self.rebuildPending else { return }
            self.rebuildPending = true
            self.micRebuildQueue.asyncAfter(deadline: .now() + 0.25) { [weak self] in
                guard let self else { return }
                self.rebuildPending = false
                guard self.isCapturing else { return }
                self.rebuildMicGraph()
            }
        }
    }

    /// Tear down and rebuild the mic tap against the new input device. Runs on
    /// `micRebuildQueue`. Retries every second on failure — a Bluetooth device
    /// often needs a moment to settle before it reports a usable format.
    private func rebuildMicGraph() {
        HelperLog.write("audio: rebuilding mic graph")
        micEngine.stop()
        if micTapInstalled {
            micEngine.inputNode.removeTap(onBus: 0)
            micTapInstalled = false
        }
        do {
            try installMicTapAndStart()
            HelperLog.write("audio: mic graph rebuilt OK")
        } catch {
            HelperLog.write("audio: mic graph rebuild failed (\(error)) — retry in 1s")
            micRebuildQueue.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                guard let self, self.isCapturing else { return }
                self.rebuildMicGraph()
            }
        }
    }

    /// Convert one mic buffer to 48 kHz mono float32. Returns nil on failure.
    /// AVAudioConverter is fed one input buffer per call — standard pattern for
    /// chunked real-time sample-rate conversion.
    ///
    /// The tap delivers buffers in the input device's own format, which
    /// changes when the device changes, so the converter is built lazily and
    /// rebuilt whenever the live buffer format no longer matches it.
    private func resampleMic(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        if micConverter?.inputFormat != buffer.format {
            micConverter = AVAudioConverter(from: buffer.format, to: micTargetFormat)
        }
        guard let converter = micConverter else { return buffer }
        let ratio = micTargetFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(
            pcmFormat: micTargetFormat, frameCapacity: capacity
        ) else { return nil }

        var fed = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if fed {
                status.pointee = .noDataNow
                return nil
            }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        if let error {
            NSLog(
                "[GlassSidebar] mic resample failed: %@",
                String(describing: error)
            )
            return nil
        }
        return out.frameLength > 0 ? out : nil
    }

    /// Root-mean-square of a PCM buffer's first channel, normalized to [0, 1]
    /// for typical speech levels. Returns 0 for empty / silent buffers.
    static func computeRMS(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.floatChannelData?[0] else { return 0 }
        let count = Int(buffer.frameLength)
        if count == 0 { return 0 }
        var sumSquares: Float = 0
        for i in 0..<count {
            let s = channelData[i]
            sumSquares += s * s
        }
        return (sumSquares / Float(count)).squareRoot()
    }

    /// Must be called from `rmsQueue`. Throttles RMS emission to 10 Hz.
    private func maybeEmitRMSLocked() {
        let now = Date().timeIntervalSince1970
        if now - lastRMSEmittedAt < 0.1 {
            return
        }
        lastRMSEmittedAt = now
        let payload: [String: Any] = [
            "type": "rms",
            "mic": lastMicRMS,
            "sys": lastSysRMS,
            "ts_ms": Int(now * 1000),
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8)
        else { return }
        sink?.sendText(text)
    }

    private func startSystemCapture() async throws {
        let content = try await SCShareableContent.current
        HelperLog.write(
            "startSystemCapture: displays=\(content.displays.count) "
                + "windows=\(content.windows.count)"
        )
        guard let display = content.displays.first else {
            HelperLog.write("startSystemCapture: NO DISPLAY available — aborting")
            return
        }
        let filter = SCContentFilter(display: display, excludingWindows: [])

        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.excludesCurrentProcessAudio = true
        cfg.sampleRate = Int(mixSampleRate)
        cfg.channelCount = 1

        let stream = SCStream(filter: filter, configuration: cfg, delegate: self)
        try stream.addStreamOutput(
            self,
            type: .audio,
            sampleHandlerQueue: .global(qos: .userInteractive)
        )
        HelperLog.write("startSystemCapture: output added, calling startCapture")
        try await stream.startCapture()
        scStream = stream
        HelperLog.write("startSystemCapture: startCapture returned without error")
    }
}

extension AudioCapture: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        HelperLog.write("SCStream didStopWithError: \(error)")
        NSLog("AudioCapture system stream stopped: \(error)")
    }
}

extension AudioCapture: SCStreamOutput {
    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of type: SCStreamOutputType
    ) {
        guard type == .audio else { return }
        guard sampleBuffer.dataReadiness == .ready else {
            HelperLog.write("system buffer dropped: dataReadiness not ready")
            return
        }
        guard let buffer = sampleBuffer.toAVAudioPCMBuffer() else {
            HelperLog.write("system buffer dropped: toAVAudioPCMBuffer failed")
            return
        }
        if !loggedFirstSysBuffer {
            loggedFirstSysBuffer = true
            HelperLog.write(
                "system audio: FIRST BUFFER ok — frames=\(buffer.frameLength) "
                    + "rate=\(buffer.format.sampleRate)"
            )
        }
        let sysRMS = AudioCapture.computeRMS(buffer)
        rmsQueue.async { [weak self] in
            guard let self else { return }
            self.lastSysRMS = sysRMS
            self.maybeEmitRMSLocked()
        }
        if let frame = encoder.encode(buffer: buffer) {
            sink?.send(channel: .system, opusFrame: frame)
        }
    }
}

extension CMSampleBuffer {
    /// Convert a CMSampleBuffer (from ScreenCaptureKit audio) into an
    /// AVAudioPCMBuffer the OpusEncoder can read.
    func toAVAudioPCMBuffer() -> AVAudioPCMBuffer? {
        guard let formatDesc = CMSampleBufferGetFormatDescription(self),
              var asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDesc)?.pointee else {
            return nil
        }
        guard let format = AVAudioFormat(streamDescription: &asbd) else { return nil }
        let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(self))
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else {
            return nil
        }
        buffer.frameLength = frameCount
        CMSampleBufferCopyPCMDataIntoAudioBufferList(
            self,
            at: 0,
            frameCount: Int32(frameCount),
            into: buffer.mutableAudioBufferList
        )
        return buffer
    }
}
