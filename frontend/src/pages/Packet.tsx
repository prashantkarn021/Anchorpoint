import {
  Check,
  Download,
  FileText,
  FolderArchive,
  Link2,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { useAssessment, usePacket, useProfile, useRecords } from "../api/hooks";
import { errorMessage, useToast } from "../components/overlay";
import {
  Button,
  Card,
  CardHeader,
  ErrorState,
  LoadingBlock,
  PageHeader,
  SeverityBadge,
} from "../components/ui";
import { ASSESSMENT_LABEL, FACTOR_LONG } from "../lib/format";

export function Packet() {
  const profile = useProfile();
  const assessment = useAssessment();
  const records = useRecords();
  const packet = usePacket();
  const toast = useToast();
  const [url, setUrl] = useState<string | null>(null);

  const all = records.data ?? [];
  const counted = all.filter((r) => r.user_status !== "rejected");
  const confirmed = counted.filter((r) => r.user_status === "confirmed").length;
  const pending = counted.length - confirmed;
  const review = counted.filter((r) => r.needs_review && r.user_status === "pending").length;
  const byFactor = ([1, 2, 3] as const).map((f) => ({
    f,
    n: counted.filter((r) => r.factor === f).length,
  }));
  const context = counted.filter((r) => !r.factor).length;

  const generate = () =>
    packet.mutate(undefined, {
      onSuccess: (res) => {
        setUrl(res.url);
        toast({ tone: "success", title: "CPA packet ready" });
      },
      onError: (e) =>
        toast({ tone: "error", title: "Couldn't build the packet", body: errorMessage(e) }),
    });

  const isBlob = url?.startsWith("blob:");
  const fileName = `anchorpoint-cpa-packet-${(profile.data?.name ?? "demo").toLowerCase().replace(/\s+/g, "-")}${isBlob ? ".md" : ""}`;

  return (
    <div className="space-y-6">
      <PageHeader
        title="CPA packet"
        description="One file for your tax professional: your assessment, every finding, and an evidence index where each record links back to its source."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_21.25rem]">
        <Card>
          <CardHeader
            title="What's inside"
            subtitle={profile.data ? `Prepared for ${profile.data.name}` : undefined}
          />
          {records.isPending || assessment.isPending ? (
            <LoadingBlock rows={6} label="Loading packet contents" />
          ) : records.isError ? (
            <ErrorState error={records.error} onRetry={() => void records.refetch()} />
          ) : assessment.isError ? (
            <ErrorState error={assessment.error} onRetry={() => void assessment.refetch()} />
          ) : (
            <div className="divide-y divide-line border-t border-line">
              <div className="flex items-start gap-3 px-5 py-4">
                <FileText className="mt-0.5 size-4 text-ink-3" aria-hidden />
                <div className="text-[0.8438rem]">
                  <p className="font-medium text-ink">Tax-home assessment</p>
                  <p className="text-ink-2">
                    Score {assessment.data.score}/100 (
                    {ASSESSMENT_LABEL[assessment.data.status].toLowerCase()}),{" "}
                    {assessment.data.factors_met} of 3 factors met
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 px-5 py-4">
                <TriangleAlert className="mt-0.5 size-4 text-ink-3" aria-hidden />
                <div className="min-w-0 flex-1 text-[0.8438rem]">
                  <p className="font-medium text-ink">
                    {assessment.data.findings.length} findings with recommended actions
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {assessment.data.findings.map((f, i) => (
                      <li key={i} className="flex items-center gap-2 text-ink-2">
                        <SeverityBadge severity={f.severity} />
                        <span className="truncate">{f.title}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="flex items-start gap-3 px-5 py-4">
                <Link2 className="mt-0.5 size-4 text-ink-3" aria-hidden />
                <div className="min-w-0 flex-1 text-[0.8438rem]">
                  <p className="font-medium text-ink">
                    Evidence index: {counted.length} records, each traced to its source
                  </p>
                  <ul className="tnum mt-1.5 space-y-0.5 text-ink-2">
                    {byFactor.map(({ f, n }) => (
                      <li key={f}>
                        Factor {f} ({FACTOR_LONG[f].toLowerCase()}): {n}
                      </li>
                    ))}
                    <li>Context (assignments, pay stubs, expenses): {context}</li>
                  </ul>
                </div>
              </div>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <span className="grid size-11 place-items-center rounded-xl border border-line bg-sunken">
              <FolderArchive className="size-5 text-brand-700" aria-hidden />
            </span>
            <h2 className="mt-3 text-[0.9375rem] font-semibold text-ink">Generate packet</h2>
            <dl className="tnum mt-3 space-y-1.5 text-[0.8125rem]">
              <div className="flex justify-between">
                <dt className="text-ink-3">Confirmed by you</dt>
                <dd className="font-medium text-ink">{confirmed}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-3">Pending (marked in the packet)</dt>
                <dd className="font-medium text-ink">{pending}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-3">Rejected (left out)</dt>
                <dd className="font-medium text-ink">{all.length - counted.length}</dd>
              </div>
            </dl>
            {review > 0 ? (
              <p className="mt-3 rounded-lg bg-warn-bg px-3 py-2 text-xs text-warn">
                {review} record{review === 1 ? "" : "s"} still need{review === 1 ? "s" : ""} review.{" "}
                <Link to="/records?review=1" className="font-medium underline">
                  Review now
                </Link>
              </p>
            ) : null}
            <Button
              variant="primary"
              icon={FolderArchive}
              className="mt-4 w-full"
              loading={packet.isPending}
              onClick={generate}
            >
              {url ? "Regenerate" : "Generate CPA packet"}
            </Button>
            {url ? (
              <a
                href={url}
                download={fileName}
                target={isBlob ? undefined : "_blank"}
                rel="noopener noreferrer"
                className="mt-2 flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-good/30 bg-good-bg text-sm font-medium text-good hover:bg-good-bg/70"
              >
                <Download className="size-4" aria-hidden /> Download packet
              </a>
            ) : null}
          </Card>
          <div className="space-y-2 px-1 text-xs text-ink-3">
            <p className="flex gap-2">
              <ShieldCheck className="size-4 shrink-0 text-ink-4" aria-hidden />
              Built from live data at the moment you click. Snippets only, never full emails.
            </p>
            <p className="flex gap-2">
              <Check className="size-4 shrink-0 text-ink-4" aria-hidden />
              Not tax advice. It organizes your evidence so your CPA can decide.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
