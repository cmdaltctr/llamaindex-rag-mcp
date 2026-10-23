import { Children, useEffect, useState, type ReactNode } from "react";

// Tailwind's md and xl breakpoints, so the columns change where the old grid did.
const TWO_COLUMNS = "(min-width: 768px)";
const THREE_COLUMNS = "(min-width: 1280px)";

function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

function columnCount(): number {
  if (matches(THREE_COLUMNS)) return 3;
  return matches(TWO_COLUMNS) ? 2 : 1;
}

/** 1, 2 or 3 columns from the page width. Follows later changes. */
function useColumnCount(): number {
  const [count, setCount] = useState(columnCount);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const lists = [TWO_COLUMNS, THREE_COLUMNS].map((query) => window.matchMedia(query));
    const onChange = () => setCount(columnCount());
    lists.forEach((list) => list.addEventListener?.("change", onChange));
    return () => lists.forEach((list) => list.removeEventListener?.("change", onChange));
  }, []);

  return count;
}

/**
 * Masonry layout: deals the children left to right into column stacks, so a
 * tall card keeps its height without leaving a gap beside a short one. Unlike
 * CSS columns, the reading order stays left to right and a card that grows
 * while you edit it does not move to another column.
 */
export function MasonryColumns({ children }: { children: ReactNode }) {
  const count = useColumnCount();
  const columns: ReactNode[][] = Array.from({ length: count }, () => []);
  Children.toArray(children).forEach((child, index) => columns[index % count]!.push(child));

  return (
    <div className="flex items-start gap-3">
      {columns.map((items, index) => (
        <div key={index} data-testid="masonry-column" className="flex min-w-0 flex-1 flex-col gap-3">
          {items}
        </div>
      ))}
    </div>
  );
}
