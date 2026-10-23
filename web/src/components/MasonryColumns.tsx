import { Children, isValidElement, useCallback, useLayoutEffect, useRef, useState, type ReactNode } from "react";

// A column is at least this wide; the gap matches `gap-3`. Three columns at most.
const MIN_COLUMN_PX = 300;
const GAP_PX = 12;
const MAX_COLUMNS = 3;

/** How many columns fit in *width* pixels: 1 to 3. */
export function columnsFor(width: number): number {
  return Math.max(1, Math.min(MAX_COLUMNS, Math.floor((width + GAP_PX) / (MIN_COLUMN_PX + GAP_PX))));
}

/** Each item, in order, goes to the column that is shortest so far; a tie goes to the leftmost. */
export function shortestColumnPlacement(heights: number[], count: number): number[] {
  const totals = new Array<number>(count).fill(0);
  return heights.map((height) => {
    const column = totals.indexOf(Math.min(...totals));
    totals[column]! += height;
    return column;
  });
}

type Layout = { count: number; columns: number[] };

function sameLayout(a: Layout, b: Layout): boolean {
  return a.count === b.count && a.columns.length === b.columns.length && a.columns.every((column, index) => column === b.columns[index]);
}

/**
 * Masonry layout: puts each card in the shortest column, so a tall card keeps
 * its height without leaving a gap beside short ones. The column count comes
 * from the width of the area itself. Cards are placed again when the area or
 * a card changes size, but not while focus is inside the area, so a card you
 * are editing does not jump to another column. Placement catches up when
 * focus leaves.
 */
export function MasonryColumns({ children }: { children: ReactNode }) {
  const items = Children.toArray(children);
  const keys = items.map((item, index) => (isValidElement(item) && item.key !== null ? String(item.key) : String(index)));
  const keyList = keys.join("|");
  const [layout, setLayout] = useState<Layout>({ count: 1, columns: keys.map(() => 0) });
  const rootRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef(new Map<string, HTMLDivElement>());
  const observerRef = useRef<ResizeObserver | null>(null);
  const keysRef = useRef(keys);

  const relayout = useCallback((force: boolean) => {
    const root = rootRef.current;
    if (root === null) return;
    if (!force && root.contains(document.activeElement)) return;
    const current = keysRef.current;
    const count = columnsFor(root.getBoundingClientRect().width);
    const heights = current.map((key) => itemRefs.current.get(key)?.getBoundingClientRect().height ?? 0);
    // No layout engine (tests, a hidden tab): deal the cards left to right.
    const columns = heights.every((height) => height === 0)
      ? current.map((_, index) => index % count)
      : shortestColumnPlacement(heights, count);
    const next = { count, columns };
    setLayout((previous) => (sameLayout(previous, next) ? previous : next));
  }, []);

  // A new set of cards is placed at once, even while focus is inside.
  useLayoutEffect(() => {
    keysRef.current = keyList.split("|");
    relayout(true);
  }, [keyList, relayout]);

  // One observer for the area and every card. A card that moves to another
  // column gets a new element, which its ref callback below observes.
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (root === null) return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => relayout(false));
    });
    observerRef.current = observer;
    observer.observe(root);
    itemRefs.current.forEach((node) => observer.observe(node));
    const onFocusOut = (event: FocusEvent) => {
      if (!(event.relatedTarget instanceof Node && root.contains(event.relatedTarget))) relayout(true);
    };
    root.addEventListener("focusout", onFocusOut);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      observerRef.current = null;
      root.removeEventListener("focusout", onFocusOut);
    };
  }, [relayout]);

  const placed = layout.columns.length === items.length ? layout.columns : items.map((_, index) => index % layout.count);
  const columns: ReactNode[][] = Array.from({ length: layout.count }, () => []);
  items.forEach((item, index) => {
    const key = keys[index]!;
    columns[Math.min(placed[index]!, layout.count - 1)]!.push(
      <div
        key={key}
        data-masonry-item=""
        ref={(node) => {
          if (node === null) return;
          itemRefs.current.set(key, node);
          observerRef.current?.observe(node);
          return () => {
            observerRef.current?.unobserve(node);
            if (itemRefs.current.get(key) === node) itemRefs.current.delete(key);
          };
        }}
      >
        {item}
      </div>,
    );
  });

  return (
    <div ref={rootRef} data-testid="masonry" className="flex items-start gap-3">
      {columns.map((column, index) => (
        <div key={index} data-testid="masonry-column" className="flex min-w-0 flex-1 flex-col gap-3">
          {column}
        </div>
      ))}
    </div>
  );
}
