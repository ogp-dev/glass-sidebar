/// Human "X ago" label for how long ago something happened.
/// `< 10s` → "just now", `< 60s` → "Ns ago", else "M:SS ago".
export function formatAgo(elapsedMs: number): string {
  const s = Math.max(0, Math.floor(elapsedMs / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${String(rem).padStart(2, "0")} ago`;
}
