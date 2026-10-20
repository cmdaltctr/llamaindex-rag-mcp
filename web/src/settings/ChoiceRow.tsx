import { sourceText } from "./connectionWords";

export const SOURCE = "text-meta text-muted-foreground";

/** One row of a provider and model choice: label, value and source. An empty value shows as "Not set". */
export function ChoiceRow({ label, value, source }: { label: string; value: string; source: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className={SOURCE}>{label}</p>
      {value === "" ? (
        <p className="text-ui">Not set</p>
      ) : (
        <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
          {value}
        </code>
      )}
      <p className={SOURCE}>{sourceText(source)}</p>
    </div>
  );
}
