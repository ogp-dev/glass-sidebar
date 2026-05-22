import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import { App } from "./app";
import { env } from "./env";
import "./index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider publishableKey={env.clerkPublishableKey}>
      <QueryClientProvider client={queryClient}>
        <App />
        <Toaster theme="dark" richColors />
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
);
