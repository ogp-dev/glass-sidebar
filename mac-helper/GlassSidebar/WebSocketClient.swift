import Foundation

/// Receives lifecycle + control-channel signals from the audio WebSocket.
/// SessionManager conforms so the dashboard's Stop button (which the backend
/// translates into a text frame on this WS) can tear down the audio engine.
protocol WebSocketClientDelegate: AnyObject {
    /// Backend sent `{"type":"shutdown"}` over the control channel.
    func shouldShutdown()
    /// The WS closed unexpectedly (network drop, server-side close, etc.).
    func webSocketDidClose()
}

/// Streams audio frames to the backend over a single WebSocket. Conforms to
/// AudioFrameSink so the AudioCapture can hand it tagged frames directly.
///
/// Per-frame format on the wire (binary): 1 byte channel tag (0x01 mic /
/// 0x02 system) followed by the raw PCM payload. The backend bridges mic to
/// Deepgram and forwards RMS text frames to the dashboard.
///
/// Inbound: backend may send text frames like `{"type":"shutdown"}`. We
/// decode and dispatch to the delegate.
final class WebSocketClient: AudioFrameSink {
    private let url: URL
    private let authToken: String?
    private var task: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)
    private var isOpen: Bool = false

    weak var delegate: WebSocketClientDelegate?

    init(url: URL, authToken: String? = nil) {
        self.url = url
        self.authToken = authToken
    }

    func connect() {
        var req = URLRequest(url: url)
        if let token = authToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        task = session.webSocketTask(with: req)
        task?.resume()
        isOpen = true
        receive()
    }

    func disconnect() {
        isOpen = false
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
    }

    // MARK: - AudioFrameSink

    func send(channel: AudioChannel, opusFrame: Data) {
        var prefixed = Data()
        prefixed.append(channel.rawValue)
        prefixed.append(opusFrame)
        task?.send(.data(prefixed)) { error in
            if let error {
                NSLog("WebSocketClient send error: \(error)")
            }
        }
    }

    func sendText(_ text: String) {
        task?.send(.string(text)) { error in
            if let error {
                NSLog("WebSocketClient sendText error: \(error)")
            }
        }
    }

    // MARK: - Inbound

    private func receive() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let error):
                NSLog("WebSocketClient receive error: \(error)")
                if self.isOpen {
                    self.isOpen = false
                    self.delegate?.webSocketDidClose()
                }
                return
            case .success(let message):
                switch message {
                case .string(let text):
                    self.handleTextFrame(text)
                case .data(let data):
                    NSLog("WebSocketClient unexpected binary inbound (%d bytes)", data.count)
                @unknown default:
                    break
                }
                if self.isOpen {
                    self.receive()  // pump
                }
            }
        }
    }

    private func handleTextFrame(_ text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            NSLog("WebSocketClient ignored unparseable text frame: %@", text.prefix(120) as CVarArg)
            return
        }
        let kind = obj["type"] as? String
        if kind == "shutdown" {
            delegate?.shouldShutdown()
        }
        // Other inbound text kinds reserved for Plan D.
    }
}
