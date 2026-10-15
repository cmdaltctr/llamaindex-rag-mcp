/** A stand-in for the browser `EventSource` that tests drive by hand. */
export class FakeEventSource {
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

  static reset(): void {
    FakeEventSource.instances = [];
  }
}
