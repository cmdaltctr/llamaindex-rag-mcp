/**
 * jsdom lacks the layout APIs React Flow reads. This follows the shim in the
 * React Flow testing guide (reactflow.dev/learn/advanced-use/testing).
 */
class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    // React Flow 12.12 also reads `contentRect`, which the guide's shim omits.
    const contentRect = { width: 800, height: 600 } as DOMRectReadOnly;
    setTimeout(() => this.callback([{ target, contentRect } as ResizeObserverEntry], this as unknown as ResizeObserver), 0);
  }

  unobserve() {}

  disconnect() {}
}

class DOMMatrixReadOnlyStub {
  m22: number;

  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([1-9.])\)/)?.[1];
    this.m22 = scale !== undefined ? Number(scale) : 1;
  }
}

let installed = false;

export function mockReactFlow(): void {
  if (installed) return;
  installed = true;
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
  (globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = DOMMatrixReadOnlyStub;
  Object.defineProperties(HTMLElement.prototype, {
    offsetHeight: {
      configurable: true,
      get(this: HTMLElement) {
        return parseFloat(this.style.height) || 1;
      },
    },
    offsetWidth: {
      configurable: true,
      get(this: HTMLElement) {
        return parseFloat(this.style.width) || 1;
      },
    },
  });
  (SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
    ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;
}
