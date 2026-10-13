import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { emptyDraft } from "./graph";
import { readDraft, writeDraft } from "./storage";
import { useDraft } from "./useDraft";

describe("useDraft", () => {
  beforeEach(() => window.localStorage.clear());

  it("does not save the empty placeholder for a pipeline with no stored draft", () => {
    renderHook(() => useDraft("pipe-1"));
    // A reload must leave room for the saved revision to load.
    expect(readDraft("pipe-1")).toBeNull();
  });

  it("keeps an existing stored draft and saves edits", () => {
    const stored = emptyDraft();
    writeDraft("pipe-2", stored);
    const { result } = renderHook(() => useDraft("pipe-2"));
    expect(result.current.draft).toEqual(stored);
    act(() => result.current.update((draft) => ({ ...draft })));
    expect(readDraft("pipe-2")).not.toBeNull();
  });

  it("saves a draft once it replaces the placeholder", () => {
    const { result } = renderHook(() => useDraft("pipe-3"));
    act(() => result.current.replace("pipe-3", emptyDraft()));
    expect(readDraft("pipe-3")).not.toBeNull();
  });
});
