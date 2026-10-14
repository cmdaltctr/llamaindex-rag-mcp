import { useState, type ReactNode } from "react";

interface OneTimeSecretProps {
  title: string;
  secret: string;
  children?: ReactNode;
  onHide: () => void;
}

/**
 * Shows a secret that the server returns only once. The secret lives in
 * component state only: never in a URL, browser storage or a log.
 */
export function OneTimeSecret({ title, secret, children, onHide }: OneTimeSecretProps) {
  const [copy, setCopy] = useState<string>("");

  async function copySecret() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopy("Copied.");
    } catch {
      setCopy("Copy failed. Select the token and copy it by hand.");
    }
  }

  return (
    <section className="one-time-secret notice notice--warning" aria-label={title}>
      <h3 className="type-section-title">{title}</h3>
      <code className="one-time-secret__value type-code" dir="ltr">
        {secret}
      </code>
      <p className="type-meta">Shown once. OMRG cannot show it again. Copy it now, then hide it.</p>
      {children}
      <div className="button-row">
        <button type="button" className="button button--small button--tinted" onClick={() => void copySecret()}>
          Copy token
        </button>
        <button type="button" className="button button--small button--ghost" onClick={onHide}>
          Hide token
        </button>
      </div>
      <p className="type-meta" role="status">
        {copy}
      </p>
    </section>
  );
}
