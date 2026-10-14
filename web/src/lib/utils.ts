import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Token names that tailwind-merge cannot classify on its own. Without them it
// reads `text-ui` as a colour and drops it next to `text-primary-label`.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "page-title",
            "section-title",
            "subsection-title",
            "ui",
            "meta",
            "code",
          ],
        },
      ],
      rounded: [{ rounded: ["control", "small", "panel"] }],
    },
  },
});

/** Join class names and resolve conflicting Tailwind utilities (later wins). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
