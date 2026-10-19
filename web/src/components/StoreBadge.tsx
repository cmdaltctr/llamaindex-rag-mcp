import { useState } from "react";
import type { VectorStoreInfo } from "../api/documents";
import { cn } from "../lib/utils";

/**
 * The vector database of a collection: logo and label. The logo is found by
 * convention at `integrations/vector-stores/<name>.png`, sits on a light
 * tile in a fixed square box, so logos of any shape and colour keep the same
 * height and stay visible in both themes. It is decorative:
 * the label is the accessible text. A missing logo leaves the label alone.
 */
export function StoreBadge({ store, className }: { store: VectorStoreInfo; className?: string }) {
  const [logoMissing, setLogoMissing] = useState(false);
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5 text-meta text-muted-foreground", className)}>
      {logoMissing ? null : (
        <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-small bg-white p-px">
          <img
            src={`${import.meta.env.BASE_URL}integrations/vector-stores/${store.name}.png`}
            alt=""
            width={20}
            height={20}
            className="size-full object-contain"
            onError={() => setLogoMissing(true)}
          />
        </span>
      )}
      <span className="truncate">{store.label}</span>
    </span>
  );
}
