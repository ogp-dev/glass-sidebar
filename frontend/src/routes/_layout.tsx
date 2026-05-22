import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/clerk-react";

export function Layout() {
  // The live and review routes render their own full headers — only the home
  // route needs this shared chrome.
  const isHome = useRouterState({
    select: (s) => s.location.pathname === "/",
  });

  return (
    <div className="min-h-screen flex flex-col">
      {isHome && (
        <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
          <Link
            to="/"
            className="text-sm font-medium tracking-wide text-slate-200 hover:text-white transition-colors"
          >
            GLASS SIDEBAR
          </Link>
          <SignedIn>
            <UserButton />
          </SignedIn>
          <SignedOut>
            <SignInButton mode="modal" />
          </SignedOut>
        </header>
      )}
      <main className="flex-1">
        <SignedIn>
          <Outlet />
        </SignedIn>
        <SignedOut>
          <div className="p-12 text-center text-slate-400 space-y-4">
            <p>Sign in to continue.</p>
            <SignInButton mode="modal">
              <button className="press rounded-md bg-gradient-to-r from-violet-500/80 to-sky-500/80 hover:from-violet-500 hover:to-sky-500 px-4 py-2 text-[13px] font-semibold text-white">
                Sign in
              </button>
            </SignInButton>
          </div>
        </SignedOut>
      </main>
    </div>
  );
}
