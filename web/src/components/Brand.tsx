import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { healthQuery } from "../api/queries";
import { cn } from "../lib/utils";

/**
 * The OMRS mark and name. The mark is decorative: the name beside it is the
 * accessible text, and stays in the page as screen-reader text when `hideName`
 * is set (the collapsed navigation). `showVersion` adds the server's package
 * version, and shows nothing while the health call has no answer.
 */
export function Brand({
  hideName = false,
  showVersion = false,
  className,
}: {
  hideName?: boolean;
  showVersion?: boolean;
  className?: string;
}) {
  const health = useQuery({ ...healthQuery(useApi()), enabled: showVersion });
  const version = showVersion && !hideName ? health.data?.version : undefined;
  return (
    <span className={cn("flex min-w-0 items-center gap-2", className)}>
      <img src={`${import.meta.env.BASE_URL}omrs-logo.svg`} alt="" width={24} height={24} className="size-6 shrink-0" />
      <span className={cn("text-section-title font-semibold", hideName && "sr-only")}>OMRS</span>
      {version ? <span className="truncate text-meta text-muted-foreground">v{version}</span> : null}
    </span>
  );
}
