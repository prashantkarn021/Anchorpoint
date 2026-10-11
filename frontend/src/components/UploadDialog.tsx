import clsx from "clsx";
import { FileImage, FileText, FileUp, Trash2, Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { useUpload } from "../api/hooks";
import type { LedgerRecord } from "../api/types";
import { recordTypeLabel } from "../lib/format";
import { errorMessage, Modal, useToast } from "./overlay";
import { useRecordLink } from "./RecordDrawer";
import { Button, Confidence } from "./ui";

export const ACCEPTED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/heic",
];
export const MAX_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 10;

export function validateFiles(files: File[]): { ok: File[]; errors: string[] } {
  const ok: File[] = [];
  const errors: string[] = [];
  for (const f of files) {
    const typeOk = ACCEPTED_TYPES.includes(f.type) || /\.(pdf|png|jpe?g|webp|heic)$/i.test(f.name);
    if (!typeOk) errors.push(`${f.name}: only PDF, PNG, JPG, WEBP or HEIC files`);
    else if (f.size > MAX_BYTES) errors.push(`${f.name}: larger than 10 MB`);
    else if (f.size === 0) errors.push(`${f.name}: file is empty`);
    else ok.push(f);
  }
  if (ok.length > MAX_FILES) {
    errors.push(`Up to ${MAX_FILES} files at a time`);
    return { ok: ok.slice(0, MAX_FILES), errors };
  }
  return { ok, errors };
}

function fmtSize(n: number) {
  return n < 1024 * 1024
    ? `${Math.max(1, Math.round(n / 1024))} KB`
    : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [drag, setDrag] = useState(false);
  const [created, setCreated] = useState<LedgerRecord[] | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const upload = useUpload();
  const toast = useToast();
  const openRecord = useRecordLink();

  const add = (list: FileList | null) => {
    if (!list) return;
    const { ok, errors: errs } = validateFiles([...files, ...Array.from(list)]);
    setFiles(ok);
    setErrors(errs);
  };

  const reset = () => {
    setFiles([]);
    setErrors([]);
    setCreated(null);
    upload.reset();
  };

  const close = () => {
    reset();
    onClose();
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    add(e.dataTransfer.files);
  };

  const submit = () =>
    upload.mutate(files, {
      onSuccess: (recs) => {
        setCreated(recs);
        setFiles([]);
        toast({
          tone: "success",
          title: `${recs.length} record${recs.length === 1 ? "" : "s"} extracted`,
        });
      },
      onError: (e) => toast({ tone: "error", title: "Upload failed", body: errorMessage(e) }),
    });

  return (
    <Modal
      open={open}
      onClose={close}
      title="Add receipts and documents"
      description="Paper receipts, PDFs, or screenshots of texts. The agent reads each one and files it with its source."
      footer={
        created ? (
          <>
            <Button variant="ghost" onClick={reset}>
              Upload more
            </Button>
            <Button variant="primary" onClick={close}>
              Done
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={close} disabled={upload.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={Upload}
              onClick={submit}
              disabled={!files.length}
              loading={upload.isPending}
            >
              {upload.isPending ? "Reading…" : `Upload ${files.length || ""}`.trim()}
            </Button>
          </>
        )
      }
    >
      {created ? (
        <div>
          <p className="text-sm text-ink-2">
            The agent created these records. Open one to check its fields.
          </p>
          <ul className="mt-3 divide-y divide-line rounded-xl border border-line">
            {created.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => {
                    close();
                    openRecord(r.id);
                  }}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sunken"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink">
                      {recordTypeLabel(r.type)}
                    </span>
                    <span className="block truncate text-xs text-ink-3">{r.source.snippet}</span>
                  </span>
                  <Confidence value={r.confidence} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={clsx(
              "flex flex-col items-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
              drag ? "border-brand-400 bg-brand-50" : "border-line-strong bg-canvas/50",
            )}
          >
            <span className="grid size-11 place-items-center rounded-full border border-line bg-surface">
              <FileUp className="size-5 text-brand-700" aria-hidden />
            </span>
            <p className="mt-3 text-sm font-medium text-ink">Drag files here</p>
            <p className="mt-1 text-xs text-ink-3">
              PDF, PNG, JPG, WEBP or HEIC · up to 10 MB each
            </p>
            <Button className="mt-4" size="sm" onClick={() => input.current?.click()}>
              Choose files
            </Button>
            <input
              ref={input}
              type="file"
              multiple
              accept={ACCEPTED_TYPES.join(",") + ",.heic"}
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
          {errors.length ? (
            <ul role="alert" className="mt-3 space-y-1 text-[13px] text-high">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : null}
          {files.length ? (
            <ul className="mt-4 divide-y divide-line rounded-xl border border-line">
              {files.map((f, i) => {
                const Icon = f.type.startsWith("image/") ? FileImage : FileText;
                return (
                  <li key={`${f.name}-${i}`} className="flex items-center gap-3 px-4 py-2.5">
                    <Icon className="size-4 shrink-0 text-ink-3" aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{f.name}</span>
                    <span className="tnum text-xs text-ink-4">{fmtSize(f.size)}</span>
                    <button
                      type="button"
                      className="text-ink-4 hover:text-high"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => setFiles(files.filter((_, j) => j !== i))}
                      disabled={upload.isPending}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
          <p className="mt-4 text-xs text-ink-4">
            Text messages can't be read by a web app. Forward them or upload a screenshot instead.
          </p>
        </>
      )}
    </Modal>
  );
}
