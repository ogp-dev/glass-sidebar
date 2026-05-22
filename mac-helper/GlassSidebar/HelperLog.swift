import Foundation

/// Lightweight file logger for the helper.
///
/// macOS redacts NSLog string content as `<private>` in the unified log, so
/// when debugging remotely we can't see what the helper is doing. This appends
/// plain timestamped lines to a file that can be read (or `tail -f`'d) over
/// SSH. Cheap, serial, best-effort — never throws.
enum HelperLog {
    private static let path = "/tmp/glass-helper.log"
    private static let queue = DispatchQueue(label: "glass.helperlog")

    static func write(_ message: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "\(stamp) \(message)\n"
        queue.async {
            guard let data = line.data(using: .utf8) else { return }
            if let handle = FileHandle(forWritingAtPath: path) {
                defer { try? handle.close() }
                _ = try? handle.seekToEnd()
                try? handle.write(contentsOf: data)
            } else {
                try? data.write(to: URL(fileURLWithPath: path))
            }
        }
    }
}
