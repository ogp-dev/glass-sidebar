import AppKit
import Foundation

/// DTO matching backend's `Session` model (subset — only fields we read).
struct SessionDTO: Decodable {
    let id: String
    let name: String
    let state: String
}

/// Orchestrates a single recording session: creates a session on the backend,
/// opens the dashboard URL in the user's browser, then starts audio + the
/// WebSocket stream. `stopSession` tears everything down.
///
/// Singleton — both MenuBarView and AppDelegate (URL scheme handler) drive
/// this instance, so they need a shared identity.
final class SessionManager {
    static let shared = SessionManager()

    private var capture: AudioCapture?
    private var ws: WebSocketClient?

    func startSession(name: String, onStatus: @escaping (String) -> Void) async {
        guard let token = Config.effectiveAuthToken else {
            onStatus("Open Glass Sidebar in your browser and start a session.")
            return
        }
        let backend = Config.effectiveBackendURL

        do {
            let sessionID: String

            if let existing = Config.effectiveSessionId, !existing.isEmpty {
                // Reuse existing session (from frontend setup / URL scheme)
                sessionID = existing
                onStatus("Joining session \(existing.prefix(8))…")
            } else {
                // Create new session from scratch (no docket)
                var req = URLRequest(url: backend.appendingPathComponent("api/sessions"))
                req.httpMethod = "POST"
                req.addValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                req.addValue("application/json", forHTTPHeaderField: "Content-Type")
                req.httpBody = try JSONEncoder().encode(["name": name])

                let (data, response) = try await URLSession.shared.data(for: req)
                guard let http = response as? HTTPURLResponse, http.statusCode == 201 else {
                    onStatus("Session create failed: \(response)")
                    return
                }
                let session = try JSONDecoder().decode(SessionDTO.self, from: data)
                sessionID = session.id
                onStatus("Connecting…")
            }

            // Open dashboard in the user's browser only when we created a new
            // session here. If reusing (URL scheme launch), the browser is
            // already at the dashboard.
            if Config.effectiveSessionId == nil {
                let dashURL = Config.frontendURL.appendingPathComponent("session/\(sessionID)/live")
                NSWorkspace.shared.open(dashURL)
            }

            // Clear URL-scheme params now that we've consumed them — a later
            // launch without params shouldn't accidentally re-use this session.
            Config.urlSession = nil
            Config.urlToken = nil
            Config.urlBackend = nil

            // Audio + WS — start audio FIRST. The WebSocket only opens once
            // the mic is confirmed capturing, so a capture failure can never
            // leave a connected-but-silent socket (which the dashboard would
            // show as "live" while no transcription ever arrives).
            let wsURL = audioWSURL(sessionID: sessionID, backend: backend)
            let client = WebSocketClient(url: wsURL, authToken: token)
            client.delegate = self

            let cap = AudioCapture()
            cap.sink = client
            try await cap.start()  // throws only if the mic itself fails

            client.connect()
            self.ws = client
            self.capture = cap

            onStatus("Live: session \(sessionID.prefix(8))…")
        } catch {
            // Audio never started → no WS was opened. Nothing to tear down;
            // the orphaned objects deallocate. Dashboard shows "disconnected".
            self.capture = nil
            self.ws = nil
            onStatus("Error: \(error)")
        }
    }

    func stopSession(onStatus: @escaping (String) -> Void) async {
        await capture?.stop()
        ws?.disconnect()
        capture = nil
        ws = nil
        onStatus("Idle")
    }

    private func audioWSURL(sessionID: String, backend: URL) -> URL {
        var comps = URLComponents(url: backend, resolvingAgainstBaseURL: false)!
        comps.scheme = (comps.scheme == "https") ? "wss" : "ws"
        comps.path = "/ws/audio/\(sessionID)"
        return comps.url!
    }
}

extension SessionManager: WebSocketClientDelegate {
    /// Called when the backend sends `{"type":"shutdown"}` over the audio WS
    /// (triggered by the dashboard's Stop button → POST /sessions/:id/stop).
    /// Tear down the audio engine; helper stays running in menu bar.
    func shouldShutdown() {
        Task { @MainActor in
            await stopSession { status in
                NSLog("[GlassSidebar] shutdown received: %@", status)
            }
        }
    }

    func webSocketDidClose() {
        Task { @MainActor in
            await stopSession { _ in }
        }
    }
}
