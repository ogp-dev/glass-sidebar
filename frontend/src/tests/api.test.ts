import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api } from "@/lib/api";

describe("api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it("createSession posts JSON with Bearer token", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ id: "x", name: "t", state: "draft", created_at: "" }),
      ),
    );
    await api.createSession("t", "tok");
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(call[1].headers.Authorization).toBe("Bearer tok");
    expect(call[1].body).toBe(JSON.stringify({ name: "t" }));
  });

  it("getSession sends GET with token", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ id: "x", name: "t", state: "draft", created_at: "" }),
      ),
    );
    await api.getSession("xid", "tok");
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toContain("/api/sessions/xid");
    expect(call[1].headers.Authorization).toBe("Bearer tok");
  });

  it("throws on non-2xx", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("nope", { status: 500 }),
    );
    await expect(api.getSession("x", "tok")).rejects.toThrow();
  });

  it("cardAction posts the action body", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" })),
    );
    await api.cardAction("sid", "cid", "dismissed", "tok");
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[1].body).toBe(JSON.stringify({ action: "dismissed" }));
  });
});
