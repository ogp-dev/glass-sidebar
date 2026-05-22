export const env = {
  apiBase: import.meta.env.VITE_API_BASE ?? "",
  wsBase: import.meta.env.VITE_WS_BASE ?? "",
  clerkPublishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string,
} as const;
