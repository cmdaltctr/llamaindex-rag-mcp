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
