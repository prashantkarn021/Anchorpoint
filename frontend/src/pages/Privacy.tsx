import { Check, X } from "lucide-react";
import { Link } from "react-router";
import { Card, CardHeader, PageHeader } from "../components/ui";
import { INFO, ORDER } from "./Connections";

/** Linked from the Google OAuth consent screen. Same wording as the consent dialogs. */
export function Privacy() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Privacy"
        description="What Anchorpoint reads, what it keeps, and how to remove it. This is a hackathon demo: every person, merchant and account in it is synthetic."
      />

      <Card>
        <CardHeader title="The short version" />
        <ul className="space-y-2 border-t border-line px-5 py-4 text-sm text-ink-2">
          <li>
            Every connection is read-only. Anchorpoint never sends, edits, pays or deletes anything
            in your accounts.
          </li>
          <li>
            It keeps extracted fields and a short snippet with a source ID, never full emails or
            documents.
          </li>
          <li>Access tokens are encrypted on the server and never reach your browser.</li>
          <li>
            You can revoke any connection and delete everything it found on the{" "}
            <Link to="/connections" className="font-medium text-brand-700 hover:underline">
              Connections
            </Link>{" "}
            page.
          </li>
          <li>Nothing is shared with anyone. Not tax advice; review your results with a CPA.</li>
        </ul>
      </Card>

      {ORDER.map((p) => {
        const info = INFO[p];
        return (
          <Card key={p}>
            <CardHeader title={info.name} subtitle={`Connected via ${info.via}`} />
            <div className="grid grid-cols-1 gap-5 border-t border-line px-5 py-4 text-sm md:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-4 uppercase">
                  Reads
                </p>
                <ul className="space-y-1.5 text-ink-2">
                  {info.reads.map((r) => (
                    <li key={r} className="flex gap-2">
                      <Check className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> {r}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-4 uppercase">
                  Never
                </p>
                <ul className="space-y-1.5 text-ink-2">
                  {info.never.map((r) => (
                    <li key={r} className="flex gap-2">
                      <X className="mt-0.5 size-4 shrink-0 text-ink-4" aria-hidden /> {r}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-ink-2 md:col-span-2">
                <span className="font-medium text-ink">Keeps:</span> {info.stores}{" "}
                <span className="break-all text-ink-3">Scopes: {info.scopes.join(", ")}.</span>
              </p>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
