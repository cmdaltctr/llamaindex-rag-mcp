import { PageHeader } from "../components/PageHeader";
import { areaById } from "../lib/views";
import { PROFILE_HELP_LINES, PROFILE_HELP_TITLE } from "./profileCopy";

/** The Studio heading, its two-sentence summary and the closed "How profiles work" disclosure. */
export function StudioHeader() {
  const area = areaById("studio");
  return (
    <>
      <PageHeader title={area.label} summary={area.summary} />
      <details className="mb-4 max-w-prose">
        <summary className="cursor-pointer text-ui">{PROFILE_HELP_TITLE}</summary>
        <ul className="mt-2 flex list-disc flex-col gap-2 ps-5 text-meta text-muted-foreground">
          {PROFILE_HELP_LINES.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
    </>
  );
}
