#!/usr/bin/env bash
# Build Glass Sidebar.app — a proper .app bundle so the URL scheme +
# LSUIElement Info.plist keys take effect (raw `swift run` doesn't expose
# them to macOS LaunchServices).
#
# Output: mac-helper/build/Glass Sidebar.app
#
# This script must run on macOS. Linux Swift can compile the binary, but
# .app bundles only work when installed under /Applications on macOS.

set -euo pipefail

cd "$(dirname "$0")"

readonly EXEC_NAME="GlassSidebar"
readonly BUNDLE_NAME="Glass Sidebar.app"
readonly BUNDLE_PATH="build/${BUNDLE_NAME}"
readonly CONTENTS="${BUNDLE_PATH}/Contents"
readonly MACOS_DIR="${CONTENTS}/MacOS"
readonly RES_DIR="${CONTENTS}/Resources"

# 1. Clean slate
rm -rf "${BUNDLE_PATH}"
mkdir -p "${MACOS_DIR}" "${RES_DIR}"

# 2. Build the release executable (native arch — a universal build needs full
#    Xcode, which the dev Macs don't have; each Mac builds for itself).
echo "==> swift build -c release"
swift build -c release

# 3. Copy the executable into the bundle
cp ".build/release/${EXEC_NAME}" "${MACOS_DIR}/${EXEC_NAME}"
chmod +x "${MACOS_DIR}/${EXEC_NAME}"

# 4. Copy Info.plist (must contain CFBundleExecutable, CFBundleIdentifier,
#    CFBundleURLTypes, LSUIElement, etc — already authored at
#    GlassSidebar/Info.plist)
cp "GlassSidebar/Info.plist" "${CONTENTS}/Info.plist"

# 5. Validate the plist parses cleanly
plutil -lint "${CONTENTS}/Info.plist"

# 6. Optional icon — drop AppIcon.icns next to Info.plist if it exists
if [ -f "GlassSidebar/AppIcon.icns" ]; then
    cp "GlassSidebar/AppIcon.icns" "${RES_DIR}/AppIcon.icns"
fi

# 7. Code-sign the bundle (optional). A stable, cert-based code identity is
#    what lets macOS persist the Screen Recording (TCC) grant across rebuilds —
#    an ad-hoc signature changes every build, so macOS treats each rebuild as a
#    brand-new, unpermissioned app. Enable signing by exporting GLASS_SIGN_IDENTITY
#    (a code-signing identity name); optionally GLASS_SIGN_KEYCHAIN and
#    GLASS_SIGN_KEYCHAIN_PW to unlock a dedicated keychain first. Without it the
#    bundle is left ad-hoc-signed — fine for a first local build.
if [ -n "${GLASS_SIGN_IDENTITY:-}" ]; then
    SIGN_KEYCHAIN="${GLASS_SIGN_KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"
    if [ -n "${GLASS_SIGN_KEYCHAIN_PW:-}" ]; then
        security unlock-keychain -p "${GLASS_SIGN_KEYCHAIN_PW}" "${SIGN_KEYCHAIN}" 2>/dev/null || true
    fi
    codesign --force --deep --sign "${GLASS_SIGN_IDENTITY}" \
        --keychain "${SIGN_KEYCHAIN}" "${BUNDLE_PATH}"
    codesign --verify --verbose "${BUNDLE_PATH}" || true
else
    echo "==> skipping code-sign (export GLASS_SIGN_IDENTITY to enable)"
fi

# 8. Touch the bundle so LaunchServices picks up the new URL scheme registration
touch "${BUNDLE_PATH}"

cat <<EOF

✓ Built: ${BUNDLE_PATH}

Install:
  1. Drag "${BUNDLE_PATH}" to /Applications/
  2. First launch: right-click → Open → "Open anyway"
     (Gatekeeper warning is expected without notarization — Plan D)
  3. Grant Screen Recording + Microphone permissions when prompted
     (System Settings → Privacy & Security)

Test the URL scheme from a Terminal:
  open "glasssidebar://start?session=<UUID>&token=<TOKEN>&backend=<URL>"

EOF
