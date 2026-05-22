import AppKit
import SwiftUI

@main
struct GlassSidebarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        // We don't want a main window — the app lives in the menu bar.
        Settings {
            EmptyView()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!

    func applicationDidFinishLaunching(_ notification: Notification) {
        // When launched via `swift run` (no app bundle / no LSUIElement key),
        // macOS doesn't know this is a menu-bar app. Set the activation policy
        // explicitly so the status item renders and there's no Dock icon.
        NSApp.setActivationPolicy(.accessory)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "waveform", accessibilityDescription: "Glass Sidebar")
            // Fallback if SF Symbols can't load the image for some reason —
            // visible text is better than an invisible button.
            if button.image == nil {
                button.title = "Glass"
            }
            button.action = #selector(togglePopover)
            button.target = self
        }

        popover = NSPopover()
        popover.contentSize = NSSize(width: 300, height: 170)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: MenuBarView())

        // Print to stderr so the user knows the helper is alive even before
        // they spot the menu-bar icon. Visible in the launching Terminal.
        FileHandle.standardError.write(
            Data("Glass Sidebar ready — look for the 'waveform' (or 'Glass') icon in the menu bar.\n".utf8)
        )
    }

    @objc func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        }
    }

    // MARK: - URL scheme handling
    //
    // The dashboard's "Launch Glass Sidebar" button opens
    // glasssidebar://start?session=UUID&token=XXX&backend=URL
    // macOS routes that to this method. We parse the query params, populate
    // Config.url*, and kick off SessionManager so the helper joins the
    // browser-created session with zero terminal interaction.

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            handleURL(url)
        }
    }

    private func handleURL(_ url: URL) {
        guard url.scheme == "glasssidebar" else {
            NSLog("[GlassSidebar] ignoring URL with unknown scheme: %@", url.absoluteString)
            return
        }
        // Treat host=="start" or host==nil (path-only) as the launch verb.
        let action = url.host ?? url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard action == "start" else {
            NSLog("[GlassSidebar] ignoring URL with unknown action %@: %@", action, url.absoluteString)
            return
        }
        let comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
        var session: String?
        var token: String?
        var backend: String?
        for item in comps?.queryItems ?? [] {
            switch item.name {
            case "session": session = item.value
            case "token":   token = item.value
            case "backend": backend = item.value
            default: break
            }
        }
        guard let s = session, !s.isEmpty,
              let t = token, !t.isEmpty,
              let b = backend, !b.isEmpty
        else {
            NSLog("[GlassSidebar] URL missing required params: %@", url.absoluteString)
            return
        }
        Config.urlSession = s
        Config.urlToken = t
        Config.urlBackend = b
        Task { @MainActor in
            await SessionManager.shared.startSession(name: "(launched from web)") { status in
                NSLog("[GlassSidebar] session status: %@", status)
            }
        }
    }
}
