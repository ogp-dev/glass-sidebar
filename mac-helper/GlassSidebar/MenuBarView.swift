import AppKit
import SwiftUI

/// Menu-bar popover shown when the user opens the helper directly. The helper
/// is driven by the web app (via the glasssidebar:// URL scheme), so this
/// screen's only job is to confirm the helper is alive and point the user back
/// to the dashboard.
struct MenuBarView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Glass Sidebar").font(.headline)

            Text("Helper is ready. Start a session from the dashboard — Glass connects it automatically.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Button("Open Glass Sidebar") {
                    NSWorkspace.shared.open(Config.frontendURL)
                }
                Spacer()
                Button("Quit") { NSApp.terminate(nil) }
            }
        }
        .padding(16)
        .frame(width: 300)
    }
}
