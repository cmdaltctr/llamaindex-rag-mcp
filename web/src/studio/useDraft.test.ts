import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { emptyDraft, setTitle } from "./graph";
import { readDraft, writeDraft } from "./storage";
import { useDraft } from "./useDraft";

describe("useDraft", () => {
  it("does not save the server's graph until the user changes something", () => {
    renderHook(() => useDraft("pipe-1", () => emptyDraft("From the server")));
    // A reload must still show what the server holds.
    expect(readDraft("pipe-1")).toBeNull();
  });

  it("starts from the stored draft instead of the server's graph", () => {
    writeDraft("pipe-2", emptyDraft("Stored"));
    const { result } = renderHook(() => useDraft("pipe-2", () => emptyDraft("From the server")));
    expect(result.current.draft.layout.title).toBe("Stored");
  });

  it("saves every change under the pipeline's own key", () => {
    const { result } = renderHook(() => useDraft("pipe-3", () => emptyDraft()));
    act(() => result.current.update((draft) => setTitle(draft, "Edited")));
    expect(readDraft("pipe-3")?.layout.title).toBe("Edited");
    expect(readDraft("pipe-4")).toBeNull();
  });

  it("clears the stored draft when a revision is saved and saves again on the next change", () => {
    const { result } = renderHook(() => useDraft("pipe-5", () => emptyDraft()));
    act(() => result.current.update((draft) => setTitle(draft, "One")));
    act(() => result.current.markSaved());
    expect(readDraft("pipe-5")).toBeNull();
    expect(result.current.draft.layout.title).toBe("One");
    act(() => result.current.update((draft) => setTitle(draft, "Two")));
    expect(readDraft("pipe-5")?.layout.title).toBe("Two");
  });
});
