import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type ApiErrorKind } from "../api/client";
import { describeError } from "./errors";

const RAW = "Expected JSON from /v1/collections but received text/html (status 200). <html>stack at line 3</html>";

function error(kind: ApiErrorKind, status: number | null): ApiError {
  return new ApiError(kind, RAW, "/v1/collections", status);
}

describe("describeError", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  const cases: { name: string; error: unknown; message: RegExp; action: string }[] = [
    { name: "network", error: error("network", null), message: /local server is not reachable/i, action: "retry" },
    { name: "not-json", error: error("not-json", 200), message: /unexpected reply/i, action: "retry" },
    { name: "invalid-json", error: error("invalid-json", 200), message: /unexpected reply/i, action: "retry" },
    { name: "invalid-path", error: error("invalid-path", null), message: /address is not valid/i, action: "back" },
    { name: "http 401", error: error("http", 401), message: /session was not accepted/i, action: "reload" },
    { name: "http 403", error: error("http", 403), message: /session was not accepted/i, action: "reload" },
    { name: "http 404", error: error("http", 404), message: /could not be found/i, action: "back" },
    { name: "http 413", error: error("http", 413), message: /^That file is larger than the server's per-file limit and was not uploaded\.$/, action: "choose-file" },
    { name: "http 500", error: error("http", 500), message: /could not complete/i, action: "retry" },
    { name: "http 409", error: error("http", 409), message: /could not complete/i, action: "retry" },
    { name: "a plain Error", error: new Error(RAW), message: /something went wrong/i, action: "retry" },
    { name: "a thrown string", error: RAW, message: /something went wrong/i, action: "retry" },
  ];

  it.each(cases)("maps $name to one message and the $action action", ({ error: failure, message, action }) => {
    const friendly = describeError(failure);
    expect(friendly.message).toMatch(message);
    expect(friendly.action.kind).toBe(action);
    expect(friendly.action.label.length).toBeGreaterThan(0);
  });

  it.each(cases)("keeps the raw text of $name out of the returned value", ({ error: failure }) => {
    const friendly = describeError(failure);
    const text = JSON.stringify(friendly);
    expect(text).not.toContain("stack at line");
    expect(text).not.toContain("text/html");
    expect(text).not.toContain("/v1/collections");
    expect(friendly.message).not.toMatch(/\b(401|403|404|413|500|409)\b/);
  });

  it("logs the raw message to the console", () => {
    describeError(error("not-json", 200));
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(String(consoleError.mock.calls[0]?.join(" "))).toContain("stack at line");
  });
});
