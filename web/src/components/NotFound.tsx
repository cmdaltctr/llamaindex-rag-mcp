import { SearchX } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { Button } from "./ui/button";

interface NotFoundProps {
  /** What the route named, for example "collection" or "pipeline". */
  what: string;
  name: string;
  backHref: string;
  backLabel: string;
}

/** A route that names a collection or pipeline the server does not return. */
export function NotFound({ what, name, backHref, backLabel }: NotFoundProps) {
  return (
    <EmptyState
      icon={SearchX}
      message={`The ${what} "${name}" could not be found.`}
      action={
        <Button asChild variant="outline">
          <a href={backHref}>{backLabel}</a>
        </Button>
      }
    />
  );
}
