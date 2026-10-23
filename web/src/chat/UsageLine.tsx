import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { AnswerUsage } from "../api/documents";
import { usageCreditQuery } from "../api/queries";
import type { UsageCredit } from "../api/settings";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";

const COUNT = new Intl.NumberFormat("en-GB");

/** A cost in US dollars: four decimals under one dollar, so a small answer does not read as $0.00. */
function dollars(value: number): string {
  return `$${value.toFixed(value < 1 ? 4 : 2)}`;
}

/** The short line, such as `1,240 in · 380 out · 210 reasoning · $0.0012 · $2.81 left`. A `null` figure is left out. */
function shortLine(usage: AnswerUsage, credit: UsageCredit | undefined): string {
  const parts: string[] = [];
  if (usage.input_tokens !== null) parts.push(`${COUNT.format(usage.input_tokens)} in`);
  if (usage.output_tokens !== null) parts.push(`${COUNT.format(usage.output_tokens)} out`);
  if (usage.reasoning_tokens !== null) parts.push(`${COUNT.format(usage.reasoning_tokens)} reasoning`);
  if (usage.cost_usd !== null) parts.push(dollars(usage.cost_usd));
  if (parts.length > 0 && credit?.available) parts.push(`$${credit.remaining_usd.toFixed(2)} left`);
  return parts.join(" · ");
}

/** The full figures for the tooltip, the number of model calls included. */
function fullLines(usage: AnswerUsage, credit: UsageCredit | undefined): string[] {
  const figure = (value: number | null) => (value === null ? "not reported" : COUNT.format(value));
  const lines = [
    `Input tokens: ${figure(usage.input_tokens)}`,
    `Output tokens: ${figure(usage.output_tokens)}`,
    `Reasoning tokens: ${figure(usage.reasoning_tokens)}`,
    `Cost: ${usage.cost_usd === null ? "not reported" : `$${usage.cost_usd}`}`,
    `Model calls: ${usage.calls}`,
  ];
  if (credit?.available) lines.push(`Credit left: $${credit.remaining_usd.toFixed(2)} of $${credit.limit_usd.toFixed(2)}`);
  return lines;
}

/**
 * Tokens and cost of the latest answer, one muted line at the top right of the
 * question box. The credit query reads once and stays fresh until Chat
 * invalidates it when an answer finishes.
 */
export function UsageLine({ usage }: { usage: AnswerUsage }) {
  const credit = useQuery(usageCreditQuery(useApi())).data;
  const text = shortLine(usage, credit);
  if (text === "") return null;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Focusable, so the full figures also open from the keyboard. */}
          <p data-testid="usage-line" tabIndex={0} className="min-w-0 truncate text-end text-meta text-muted-foreground">
            {text}
          </p>
        </TooltipTrigger>
        <TooltipContent>
          {fullLines(usage, credit).map((line) => (
            <span key={line} className="block">
              {line}
            </span>
          ))}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
