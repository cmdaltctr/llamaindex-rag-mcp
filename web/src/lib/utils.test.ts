import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins truthy class names and skips falsy ones", () => {
    expect(cn("a", false, undefined, "b", { c: true, d: false })).toBe("a b c");
  });

  it("lets a later utility replace a conflicting one", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("keeps a token font size next to a token colour", () => {
    expect(cn("text-ui", "text-primary-label")).toBe("text-ui text-primary-label");
    expect(cn("text-meta", "text-muted-foreground")).toBe("text-meta text-muted-foreground");
  });

  it("replaces one token font size with another", () => {
    expect(cn("text-ui", "text-meta")).toBe("text-meta");
  });

  it("replaces one token radius with another", () => {
    expect(cn("rounded-control", "rounded-small")).toBe("rounded-small");
  });
});
