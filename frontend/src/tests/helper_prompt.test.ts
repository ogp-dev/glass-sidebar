import { describe, it, expect, beforeEach, vi } from "vitest";

import {
  shouldShowHelperBanner,
  shouldShowRecapCard,
  dismissRecap,
  isHelperReady,
  markHelperReady,
  clearHelperReady,
  launchHelper,
} from "@/lib/helper_prompt";

describe("helper_prompt", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("helper banner shows until the helper is installed", () => {
    expect(shouldShowHelperBanner()).toBe(true);
    markHelperReady();
    expect(shouldShowHelperBanner()).toBe(false);
  });

  it("recap card shows on every session until dismissed", () => {
    expect(shouldShowRecapCard()).toBe(true);
    dismissRecap();
    expect(shouldShowRecapCard()).toBe(false);
  });

  it("helper-ready flag flips with markHelperReady", () => {
    expect(isHelperReady()).toBe(false);
    markHelperReady();
    expect(isHelperReady()).toBe(true);
  });

  it("clearHelperReady removes the installed flag", () => {
    markHelperReady();
    expect(isHelperReady()).toBe(true);
    clearHelperReady();
    expect(isHelperReady()).toBe(false);
  });

  it("launchHelper opens the glasssidebar:// URL with session, token and backend", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    launchHelper("sess-123", "tok-abc");
    expect(open).toHaveBeenCalledOnce();
    const url = open.mock.calls[0][0] as string;
    expect(url).toContain("glasssidebar://start?");
    expect(url).toContain("session=sess-123");
    expect(url).toContain("token=tok-abc");
    expect(url).toContain(`backend=${encodeURIComponent(window.location.origin)}`);
    open.mockRestore();
  });
});
