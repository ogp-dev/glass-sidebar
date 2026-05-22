# Glass Sidebar — Mac Helper

Menu-bar app that captures the host's mic + system audio (everyone they hear via speakers/headphones, including remote Zoom/Riverside guests) and streams it over WebSocket to the Glass Sidebar backend.

## Build (on a Mac with Xcode / Swift 5.10+)

```bash
cd mac-helper
swift build -c release
```

The signed `.dmg` for distribution is built via Xcode (later — out of scope for v1 dev).

## Run

```bash
GLASS_BACKEND_URL=http://localhost:8000 \
GLASS_AUTH_TOKEN=<your-clerk-jwt> \
swift run GlassSidebar
```

On first launch macOS will request **Microphone** and **Screen Recording** permissions. Both are required — the helper can't capture system audio without Screen Recording (that's how macOS exposes the system audio routing model).

## Layout

- `GlassSidebar/` — executable target (menu-bar app, audio capture, WebSocket client)
- `GlassSidebarTests/` — XCTest target (tests in later tasks)

## Note for non-Mac contributors

The source code is written and version-controlled on any platform, but **building requires macOS**. The audio capture uses `ScreenCaptureKit` and `AVAudioEngine` — both macOS-only Apple frameworks.
