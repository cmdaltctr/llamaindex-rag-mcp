/** `n` with thousands separators, such as `2,048`. */
export function formatCount(n: number): string {
  return n.toLocaleString("en-GB");
}

/**
 * A check for a whole number between `min` and `max` (a bound that is `null` is not checked).
 * Returns `message` when the text is not a whole number in range, else `null`. The server
 * still judges every value; this check stops an obvious mistake before the request.
 */
export function wholeNumberIn(min: number | null, max: number | null, message: string): (text: string) => string | null {
  return (text) => {
    const value = /^-?\d+$/.test(text.trim()) ? Number(text.trim()) : Number.NaN;
    const inRange = Number.isInteger(value) && (min === null || value >= min) && (max === null || value <= max);
    return inRange ? null : message;
  };
}

/** The rule for a number between `min` and `max`, such as "Enter 1 to 8." A bound that is `null` is left out. */
export function rangeRule(min: number | null, max: number | null, whole: boolean): string {
  const shown = (n: number) => (whole ? formatCount(n) : String(n));
  if (min !== null && max !== null) return `Enter ${shown(min)} to ${shown(max)}.`;
  const what = whole ? "a whole number" : "a number";
  if (min !== null) return `Enter ${what} of at least ${shown(min)}.`;
  if (max !== null) return `Enter ${what} of at most ${shown(max)}.`;
  return `Enter ${what}.`;
}

/** Like `wholeNumberIn`, but a decimal such as `0.75` passes too. */
export function numberIn(min: number | null, max: number | null, message: string): (text: string) => string | null {
  return (text) => {
    const value = /^-?(\d+\.?\d*|\.\d+)$/.test(text.trim()) ? Number(text.trim()) : Number.NaN;
    const inRange = Number.isFinite(value) && (min === null || value >= min) && (max === null || value <= max);
    return inRange ? null : message;
  };
}
