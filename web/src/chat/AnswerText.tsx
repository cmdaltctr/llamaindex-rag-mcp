import { Children, createContext, useContext, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation, Evidence } from "../api/documents";
import { Button } from "../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { CitationPopover } from "./CitationPopover";

interface AnswerTextProps {
  text: string;
  citations: Citation[];
  evidence: Evidence[];
  collection: string;
  onShowChunk: (collection: string, chunkId: string) => void;
}

type CitationTarget = Omit<AnswerTextProps, "text">;

const CitationContext = createContext<CitationTarget | null>(null);

/**
 * Splits a text run on `[n]`. A marker becomes a button only when `n` is the
 * ordinal of a returned citation, so no citation is invented. Any other marker
 * stays text.
 */
function CitedText({ children }: { children: ReactNode }) {
  const target = useContext(CitationContext);
  return (
    <>
      {Children.map(children, (child) => {
        if (typeof child !== "string" || target === null) return child;
        return child.split(/\[(\d+)\]/).map((part, index) => {
          if (index % 2 === 0) return part;
          const citation = target.citations.find((c) => c.ordinal === Number(part));
          if (citation === undefined) return `[${part}]`;
          return (
            <CitationPopover
              key={index}
              citation={citation}
              evidence={target.evidence.find((e) => e.ordinal === citation.ordinal)}
              collection={target.collection}
              onShowChunk={target.onShowChunk}
              trigger={(props) => (
                <Button variant="link" size="inline" dir="ltr" aria-label={`Citation ${citation.ordinal}`} className="select-text px-0 align-baseline" {...props}>
                  [{part}]
                </Button>
              )}
            />
          );
        });
      })}
    </>
  );
}

const HEADING = "mt-2 font-semibold text-foreground";

/**
 * Element map for the answer. Every element that holds running text passes it
 * through `CitedText`. Code never does, so `a[1]` in code stays code. The map is
 * module-level so the elements keep their identity between renders.
 */
const ANSWER_COMPONENTS: Components = {
  p: ({ children }) => (
    <p className="whitespace-pre-line leading-relaxed">
      <CitedText>{children}</CitedText>
    </p>
  ),
  h1: ({ children }) => (
    <h1 className={`${HEADING} text-section-title`}>
      <CitedText>{children}</CitedText>
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className={`${HEADING} text-subsection-title`}>
      <CitedText>{children}</CitedText>
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className={`${HEADING} text-ui`}>
      <CitedText>{children}</CitedText>
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className={`${HEADING} text-ui`}>
      <CitedText>{children}</CitedText>
    </h4>
  ),
  h5: ({ children }) => (
    <h5 className={`${HEADING} text-ui`}>
      <CitedText>{children}</CitedText>
    </h5>
  ),
  h6: ({ children }) => (
    <h6 className={`${HEADING} text-ui`}>
      <CitedText>{children}</CitedText>
    </h6>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold">
      <CitedText>{children}</CitedText>
    </strong>
  ),
  em: ({ children }) => (
    <em>
      <CitedText>{children}</CitedText>
    </em>
  ),
  del: ({ children }) => (
    <del>
      <CitedText>{children}</CitedText>
    </del>
  ),
  ul: ({ children }) => <ul className="flex list-disc flex-col gap-2 ps-5">{children}</ul>,
  ol: ({ start, children }) => (
    <ol start={start} className="flex list-decimal flex-col gap-2 ps-5">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="whitespace-pre-line leading-relaxed [&>*+*]:mt-2">
      <CitedText>{children}</CitedText>
    </li>
  ),
  blockquote: ({ children }) => <blockquote className="border-s-2 border-border ps-3 text-muted-foreground">{children}</blockquote>,
  hr: () => <hr className="border-border" />,
  // A rejected scheme (for example javascript:) arrives with no href. It stays text.
  a: ({ href, children }) =>
    href ? (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary-label underline underline-offset-4 hover:no-underline">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  // Inline code. Inside a block, `pre` resets the box so only the block shows.
  code: ({ className, children }) => (
    <code className={`rounded-small bg-muted px-1 font-mono text-code ${className ?? ""}`}>{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-control border border-border bg-muted p-3 font-mono text-code [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  table: ({ children }) => <Table>{children}</Table>,
  thead: ({ children }) => <TableHeader>{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow>{children}</TableRow>,
  th: ({ children }) => (
    <TableHead>
      <CitedText>{children}</CitedText>
    </TableHead>
  ),
  td: ({ children }) => (
    <TableCell>
      <CitedText>{children}</CitedText>
    </TableCell>
  ),
};

/**
 * Element map for one claim. A claim is one line of the answer, so it keeps
 * only inline marks and drops block elements to their text.
 */
const CLAIM_COMPONENTS: Components = {
  p: ({ children }) => <CitedText>{children}</CitedText>,
  strong: ANSWER_COMPONENTS.strong,
  em: ANSWER_COMPONENTS.em,
  code: ANSWER_COMPONENTS.code,
};

const CLAIM_ELEMENTS = ["p", "strong", "em", "code"];

/** A line that is only a code fence has no text to render. Show it as written. */
const BARE_FENCE = /^`{3,}\w*$/;

interface ClaimListProps extends CitationTarget {
  claims: { claim: string; verdict: string; ordinals: number[] }[];
}

/**
 * The claims that failed verification, one line each. A claim renders its
 * inline code and marks, and the `[n]` it cites is a citation button.
 */
export function ClaimList({ claims, citations, evidence, collection, onShowChunk }: ClaimListProps) {
  return (
    <CitationContext.Provider value={{ citations, evidence, collection, onShowChunk }}>
      <ul aria-label="Claims that failed verification" className="flex flex-col gap-1 text-meta">
        {claims.map((item, index) => (
          <li key={index} className="break-words">
            {BARE_FENCE.test(item.claim.trim()) ? (
              item.claim.trim()
            ) : (
              <Markdown remarkPlugins={[remarkGfm]} components={CLAIM_COMPONENTS} allowedElements={CLAIM_ELEMENTS} unwrapDisallowed>
                {item.claim}
              </Markdown>
            )}{" "}
            <CitedText>{`(${item.verdict}, cites ${item.ordinals.map((n) => `[${n}]`).join(" ")})`}</CitedText>
          </li>
        ))}
      </ul>
    </CitationContext.Provider>
  );
}

/**
 * The answer rendered as markdown (GitHub flavour). The model's text is parsed
 * into React elements and never into raw HTML, so markup in it shows as text.
 * A `[n]` marker is a citation button only when `n` matches a returned citation.
 */
export function AnswerText({ text, citations, evidence, collection, onShowChunk }: AnswerTextProps) {
  return (
    <CitationContext.Provider value={{ citations, evidence, collection, onShowChunk }}>
      <div className="flex min-w-0 flex-col gap-4 break-words">
        <Markdown remarkPlugins={[remarkGfm]} components={ANSWER_COMPONENTS}>
          {text}
        </Markdown>
      </div>
    </CitationContext.Provider>
  );
}
