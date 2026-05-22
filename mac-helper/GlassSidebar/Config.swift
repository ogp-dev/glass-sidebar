import Foundation

enum Config {
    /// Backend base URL (API + WS). Override with GLASS_BACKEND_URL env var.
    static var backendURL: URL {
        if let raw = ProcessInfo.processInfo.environment["GLASS_BACKEND_URL"],
           let url = URL(string: raw) {
            return url
        }
        return URL(string: "https://glass.sinfyai.com")!
    }

    /// Frontend dashboard URL. The Mac helper opens this in the user's
    /// browser after creating a session, so they land on the live UI
    /// instead of the raw backend port. Defaults to backendURL for
    /// production (Caddy routes both to the same host) but can be set
    /// independently in dev where Vite runs on a different port.
    static var frontendURL: URL {
        if let raw = ProcessInfo.processInfo.environment["GLASS_FRONTEND_URL"],
           let url = URL(string: raw) {
            return url
        }
        return backendURL
    }

    /// Clerk JWT for authenticated API calls. For v1, read from env var;
    /// Task 19 (or later) moves this to macOS Keychain.
    static var authToken: String? {
        ProcessInfo.processInfo.environment["GLASS_AUTH_TOKEN"]
    }

    /// If set, the helper uses this existing session_id instead of creating
    /// a new one. Lets the host start setup + docket from the browser, then
    /// hand the session UUID to the helper for audio streaming.
    static var sessionId: String? {
        ProcessInfo.processInfo.environment["GLASS_SESSION_ID"]
    }

    // MARK: - URL scheme overrides
    //
    // Populated by AppDelegate.application(_:open:) when the helper is launched
    // via glasssidebar://start?session=...&token=...&backend=...
    // Cleared after SessionManager.startSession reads them so a subsequent
    // launch without params doesn't accidentally re-use stale values.

    static var urlSession: String? = nil
    static var urlToken: String? = nil
    static var urlBackend: String? = nil

    /// Resolve effective values. URL-launched values win over env, env wins
    /// over the production default.
    static var effectiveSessionId: String? {
        urlSession ?? sessionId
    }

    static var effectiveAuthToken: String? {
        urlToken ?? authToken
    }

    static var effectiveBackendURL: URL {
        if let s = urlBackend, let u = URL(string: s) {
            return u
        }
        return backendURL
    }
}
