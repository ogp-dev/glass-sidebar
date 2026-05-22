/// Pure visibility + launch logic for the optional Mac helper ("Who said what").
/// Kept free of React so it is unit-testable. State is per-browser localStorage.

const K_RECAP_DISMISSED = "glass.recapDismissed";
const K_HELPER_READY = "glass.helperReady";

/// The hosted helper artifact — served by a Caddy route outside the frontend
/// static root (see the implementation plan, Task 1).
export const HELPER_DOWNLOAD_URL = "/downloads/Glass-Sidebar.dmg";

export function isHelperReady(): boolean {
  return localStorage.getItem(K_HELPER_READY) === "true";
}

export function markHelperReady(): void {
  localStorage.setItem(K_HELPER_READY, "true");
}

export function clearHelperReady(): void {
  localStorage.removeItem(K_HELPER_READY);
}

/// The in-session helper banner shows on every live session until the helper
/// has been installed. "Maybe later" only hides it for the current session.
export function shouldShowHelperBanner(): boolean {
  return !isHelperReady();
}

export function shouldShowRecapCard(): boolean {
  return localStorage.getItem(K_RECAP_DISMISSED) !== "true";
}

export function dismissRecap(): void {
  localStorage.setItem(K_RECAP_DISMISSED, "true");
}

/// Launch the Mac helper into a session via its registered URL scheme. The
/// helper builds its audio-WS URL from `backend`; window.location.origin is the
/// public origin in prod and the Vite dev origin in dev (which proxies /ws).
export function launchHelper(sessionId: string, token: string): void {
  const url =
    `glasssidebar://start?session=${encodeURIComponent(sessionId)}` +
    `&token=${encodeURIComponent(token)}` +
    `&backend=${encodeURIComponent(window.location.origin)}`;
  window.open(url);
}
