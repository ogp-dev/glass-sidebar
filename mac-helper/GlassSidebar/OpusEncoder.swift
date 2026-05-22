import AVFoundation
import Foundation

/// v1 stub: passes through raw 16-bit PCM in little-endian.
/// TODO(perf): swap in real Opus encoding via libopus binding later. The
/// backend's Deepgram client is configured for linear16 PCM today, so this
/// is the matching wire format.
final class OpusEncoder {
    let sampleRate: Double

    init(sampleRate: Double) {
        self.sampleRate = sampleRate
    }

    /// Encode one AVAudioPCMBuffer to a Data frame.
    ///
    /// Handles both int16 and float32 input buffers — converts float32 → int16
    /// with clipping. Returns nil only if the buffer is unreadable.
    func encode(buffer: AVAudioPCMBuffer) -> Data? {
        if let int16 = buffer.int16ChannelData {
            let frameLength = Int(buffer.frameLength)
            return Data(bytes: int16[0], count: frameLength * MemoryLayout<Int16>.size)
        }
        return buffer.toInt16PCMData()
    }
}

extension AVAudioPCMBuffer {
    /// Convert float32 channel data to int16 PCM.
    func toInt16PCMData() -> Data? {
        guard let float = floatChannelData else { return nil }
        let frameLength = Int(self.frameLength)
        var ints = [Int16](repeating: 0, count: frameLength)
        let scale: Float = 32_767.0
        for i in 0..<frameLength {
            let v = max(-1.0, min(1.0, float[0][i])) * scale
            ints[i] = Int16(v)
        }
        return ints.withUnsafeBufferPointer { Data(buffer: $0) }
    }
}
