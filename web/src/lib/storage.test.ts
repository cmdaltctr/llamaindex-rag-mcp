import { afterEach, describe, expect, it, vi } from "vitest";
import { readStored, removeStored, writeStored } from "./storage";

const isCount = (value: unknown): value is { count: number } =>
  typeof value === "object" && value !== null && typeof (value as { count?: unknown }).count === "number";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("stored values", () => {
  it("round-trips a value that passes its validator", () => {
    writeStored("k", { count: 2 });
    expect(readStored("k", isCount)).toEqual({ count: 2 });
  });

  it("writes plain JSON with no version field", () => {
    writeStored("k", { count: 2 });
    expect(window.localStorage.getItem("k")).toBe('{"count":2}');
  });

  it("returns null when nothing is stored", () => {
    expect(readStored("k", isCount)).toBeNull();
  });

  it("ignores and removes malformed JSON", () => {
    window.localStorage.setItem("k", "{not json");
    expect(readStored("k", isCount)).toBeNull();
    expect(window.localStorage.getItem("k")).toBeNull();
  });

  it("ignores and removes a value of an old shape", () => {
    window.localStorage.setItem("k", JSON.stringify({ version: 1, view: "canvas" }));
    expect(readStored("k", isCount)).toBeNull();
    expect(window.localStorage.getItem("k")).toBeNull();
  });

  it("removes a stored key", () => {
    writeStored("k", { count: 1 });
    removeStored("k");
    expect(window.localStorage.getItem("k")).toBeNull();
  });

  it("does not throw when every storage call throws", () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("blocked");
      });
    }
    expect(() => writeStored("k", { count: 1 })).not.toThrow();
    expect(readStored("k", isCount)).toBeNull();
    expect(() => removeStored("k")).not.toThrow();
  });

  it("does not throw when the storage object is unavailable", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => writeStored("k", { count: 1 })).not.toThrow();
    expect(readStored("k", isCount)).toBeNull();
    expect(() => removeStored("k")).not.toThrow();
  });
});
