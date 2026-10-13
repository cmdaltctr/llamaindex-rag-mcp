import { vi } from "vitest";
import type { RunEventRecord } from "../../api/runs";
import type { EventSourceLike } from "../eventClient";

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export function event(sequence: number, kind: string, extra: Partial<RunEventRecord> = {}): RunEventRecord {
  return {
    run_id: "r1",
    sequence,
    kind,
    node_id: null,
    unit_id: null,
    summary: {},
    created_at: `2026-10-13T12:00:${String(sequence).padStart(2, "0")}Z`,
    ...extra,
  };
}

/** Stand-in for the browser `EventSource`. Tests push frames and errors by hand. */
export class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  private readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.readyState = 2;
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  /** Delivers one frame as the server writes it: `id:` holds the sequence. */
  frame(kind: string, data: unknown, id?: number): void {
    const message = new MessageEvent(kind, { data: JSON.stringify(data), lastEventId: id === undefined ? "" : String(id) });
    for (const listener of this.listeners.get(kind) ?? []) listener(message);
  }

  send(record: RunEventRecord): void {
    this.frame(record.kind, record, record.sequence);
  }

  /** `closed` mimics a refused stream; otherwise the browser reconnects by itself. */
  fail(closed: boolean): void {
    this.readyState = closed ? 2 : 0;
    this.onerror?.(new Event("error"));
  }

  static latest(): FakeEventSource {
    const latest = FakeEventSource.instances.at(-1);
    if (!latest) throw new Error("No event source was opened.");
    return latest;
  }
}

export function eventSourceFactory() {
  FakeEventSource.instances = [];
  return vi.fn((url: string) => new FakeEventSource(url));
}

/** A scheduler the test drives: `flush()` runs every pending callback once. */
export function manualScheduler() {
  let pending: { fn: () => void; ms: number }[] = [];
  const schedule = vi.fn((fn: () => void, ms: number) => {
    const entry = { fn, ms };
    pending.push(entry);
    return () => {
      pending = pending.filter((item) => item !== entry);
    };
  });
  return {
    schedule,
    pendingDelays: () => pending.map((item) => item.ms),
    flush() {
      const due = pending;
      pending = [];
      for (const item of due) item.fn();
    },
  };
}
