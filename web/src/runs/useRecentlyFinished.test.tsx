import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NodeRunState } from "./runState";
import { FINISH_HOLD_MS, useRecentlyFinished } from "./useRecentlyFinished";

const state = (status: NodeRunState["status"]): NodeRunState => ({ status, fallback: null, error: null, message: null, summary: null, unitId: null, startedAt: null, endedAt: null });

type Props = { states: Record<string, NodeRunState>; live: boolean | null };

function setup(initial: Props) {
  return renderHook(({ states, live }: Props) => useRecentlyFinished(states, live), { initialProps: initial });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useRecentlyFinished", () => {
  it("holds a step that finished in a live run for the hold time, then lets it go", () => {
    const view = setup({ states: { a: state("running") }, live: true });
    expect(view.result.current.size).toBe(0);
    view.rerender({ states: { a: state("succeeded") }, live: true });
    expect([...view.result.current]).toEqual(["a"]);
    act(() => void vi.advanceTimersByTime(FINISH_HOLD_MS - 1));
    expect([...view.result.current]).toEqual(["a"]);
    act(() => void vi.advanceTimersByTime(2));
    expect(view.result.current.size).toBe(0);
  });

  it("never fills for a run that was not live when watching began", () => {
    const view = setup({ states: { a: state("running") }, live: false });
    view.rerender({ states: { a: state("succeeded") }, live: false });
    expect(view.result.current.size).toBe(0);
    const unknown = setup({ states: { a: state("running") }, live: null });
    unknown.rerender({ states: { a: state("succeeded") }, live: null });
    expect(unknown.result.current.size).toBe(0);
  });

  it("ignores a step that first appears as succeeded, and one that failed", () => {
    const view = setup({ states: {}, live: true });
    view.rerender({ states: { a: state("succeeded") }, live: true });
    expect(view.result.current.size).toBe(0);
    view.rerender({ states: { a: state("succeeded"), b: state("running") }, live: true });
    view.rerender({ states: { a: state("succeeded"), b: state("failed") }, live: true });
    expect(view.result.current.size).toBe(0);
  });

  it("lets two steps that finish together go together, and keeps a later one longer", () => {
    const view = setup({ states: { a: state("running"), b: state("running") }, live: true });
    view.rerender({ states: { a: state("succeeded"), b: state("succeeded") }, live: true });
    expect([...view.result.current].sort()).toEqual(["a", "b"]);
    act(() => void vi.advanceTimersByTime(FINISH_HOLD_MS / 2));
    view.rerender({ states: { a: state("succeeded"), b: state("succeeded"), c: state("running") }, live: true });
    view.rerender({ states: { a: state("succeeded"), b: state("succeeded"), c: state("succeeded") }, live: true });
    expect([...view.result.current].sort()).toEqual(["a", "b", "c"]);
    act(() => void vi.advanceTimersByTime(FINISH_HOLD_MS / 2 + 1));
    expect([...view.result.current]).toEqual(["c"]);
    act(() => void vi.advanceTimersByTime(FINISH_HOLD_MS / 2));
    expect(view.result.current.size).toBe(0);
  });

  it("clears its timers when the canvas goes away", () => {
    const view = setup({ states: { a: state("running") }, live: true });
    view.rerender({ states: { a: state("succeeded") }, live: true });
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
