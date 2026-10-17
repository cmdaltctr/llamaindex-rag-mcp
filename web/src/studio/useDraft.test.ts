import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { emptyDraft, setSelection, setViewport } from "./graph";
import { readDraft, writeDraft } from "./storage";
import { useDraft } from "./useDraft";

describe("useDraft", () => {
  it("does not save the server's graph until the user changes something", () => {
    renderHook(() => useDraft("pipe-1", () => emptyDraft()));
    // A reload must still show what the server holds.
    expect(readDraft("pipe-1")).toBeNull();
  });

  it("starts from the stored draft instead of the server's graph", () => {
    writeDraft("pipe-2", setViewport(emptyDraft(), { x: 0, y: 0, zoom: 2 }));
    const { result } = renderHook(() => useDraft("pipe-2", () => emptyDraft()));
    expect(result.current.draft.layout.viewport.zoom).toBe(2);
  });

  it("saves every change under the pipeline's own key", () => {
    const { result } = renderHook(() => useDraft("pipe-3", () => emptyDraft()));
    act(() => result.current.update((draft) => setSelection(draft, ["dense"])));
    expect(readDraft("pipe-3")?.layout.selection).toEqual(["dense"]);
    expect(readDraft("pipe-4")).toBeNull();
  });

  it("clears the stored draft when a revision is saved and saves again on the next change", () => {
    const { result } = renderHook(() => useDraft("pipe-5", () => emptyDraft()));
    act(() => result.current.update((draft) => setSelection(draft, ["one"])));
    act(() => result.current.markSaved());
    expect(readDraft("pipe-5")).toBeNull();
    expect(result.current.draft.layout.selection).toEqual(["one"]);
    act(() => result.current.update((draft) => setSelection(draft, ["two"])));
    expect(readDraft("pipe-5")?.layout.selection).toEqual(["two"]);
  });

  describe("with persist: false", () => {
    it("keeps selection and viewport in memory and writes nothing to storage", () => {
      const { result } = renderHook(() => useDraft("pipe-6", () => emptyDraft(), { persist: false }));
      act(() => result.current.update((draft) => setSelection(draft, ["dense"])));
      act(() => result.current.update((draft) => setViewport(draft, { x: 10, y: 20, zoom: 2 })));
      expect(result.current.draft.layout.selection).toEqual(["dense"]);
      expect(result.current.draft.layout.viewport).toEqual({ x: 10, y: 20, zoom: 2 });
      expect(readDraft("pipe-6")).toBeNull();
      expect(window.localStorage.length).toBe(0);
    });

    it("ignores a stored draft and starts from the given graph", () => {
      writeDraft("pipe-7", setViewport(emptyDraft(), { x: 0, y: 0, zoom: 2 }));
      const { result } = renderHook(() => useDraft("pipe-7", () => emptyDraft(), { persist: false }));
      expect(result.current.draft.layout.viewport.zoom).toBe(1);
    });
  });
});
