import clsx from "clsx";
import {
  CalendarDays,
  CircleAlert,
  CircleCheck,
  Info,
  Landmark,
  LoaderCircle,
  Mail,
  RefreshCw,
  TriangleAlert,
  Upload,
  type LucideIcon,
} from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import type { Provider, Severity, UserStatus } from "../api/types";
import { PROVIDER_LABEL, SEVERITY_LABEL, STATUS_LABEL } from "../lib/format";

// ---- Button ----

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-brand-800 text-white hover:bg-brand-700 active:bg-brand-900 shadow-card disabled:bg-brand-800/50",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-sunken active:bg-line shadow-card disabled:text-ink-4",
  ghost: "text-ink-2 hover:bg-sunken hover:text-ink active:bg-line disabled:text-ink-4",
  danger:
    "bg-surface text-high border border-high/30 hover:bg-high-bg active:bg-high-bg disabled:opacity-50",
};

const SIZE: Record<Size, string> = {
  sm: "h-8 px-2.5 text-[13px] gap-1.5 rounded-md",
  md: "h-9 px-3.5 text-sm gap-2 rounded-lg",
};

/** Button styling for links (<Link className={buttonClass("primary")}>) so we never nest <a><button>. */
export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra?: string) {
  return clsx(
    "inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors",
    VARIANT[variant],
    SIZE[size],
    extra,
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon: Icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
    >
      {loading ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
      ) : Icon ? (
        <Icon className="size-4" aria-hidden />
      ) : null}
      {children}
    </button>
  );
}

// ---- Card ----

export function Card({
  className,
  children,
  as: As = "section",
  ...rest
}: {
  className?: string;
  children: ReactNode;
  as?: "section" | "div" | "article";
} & HTMLAttributes<HTMLElement>) {
  return (
    <As
      {...rest}
      className={clsx("rounded-xl border border-line bg-surface shadow-card", className)}
    >
      {children}
    </As>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex items-start justify-between gap-4 px-5 pt-4 pb-3", className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-[13px] text-ink-3">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

// ---- Badges ----

type Tone = "neutral" | "brand" | "good" | "warn" | "high" | "info";

const TONE: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2 border-line",
  brand: "bg-brand-50 text-brand-700 border-brand-100",
  good: "bg-good-bg text-good border-good/15",
  warn: "bg-warn-bg text-warn border-warn/15",
  high: "bg-high-bg text-high border-high/15",
  info: "bg-info-bg text-info border-info/15",
};

export function Badge({
  tone = "neutral",
  icon: Icon,
  children,
  className,
  title,
}: {
  tone?: Tone;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE[tone],
        className,
      )}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
      {children}
    </span>
  );
}

export const SEVERITY_TONE: Record<Severity, Tone> = { info: "info", warn: "warn", high: "high" };
export const SEVERITY_ICON: Record<Severity, LucideIcon> = {
  info: Info,
  warn: TriangleAlert,
  high: CircleAlert,
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={SEVERITY_TONE[severity]} icon={SEVERITY_ICON[severity]}>
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

export function StatusBadge({
  status,
  needsReview,
}: {
  status: UserStatus;
  needsReview?: boolean;
}) {
  if (status === "pending" && needsReview) {
    return (
      <Badge tone="warn" icon={TriangleAlert} title="Low confidence: not counted until you confirm">
        Needs review
      </Badge>
    );
  }
  const tone: Tone = status === "confirmed" ? "good" : status === "rejected" ? "neutral" : "brand";
  return (
    <Badge tone={tone} icon={status === "confirmed" ? CircleCheck : undefined}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

// ---- Provider ----

export const PROVIDER_ICON: Record<Provider, LucideIcon> = {
  gmail: Mail,
  calendar: CalendarDays,
  bank: Landmark,
  upload: Upload,
};

export function ProviderTag({ provider, compact }: { provider: Provider; compact?: boolean }) {
  const Icon = PROVIDER_ICON[provider];
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
      <span className="grid size-6 place-items-center rounded-md border border-line bg-sunken">
        <Icon className="size-3.5 text-ink-2" aria-hidden />
      </span>
      {compact ? (
        <span className="sr-only">{PROVIDER_LABEL[provider]}</span>
      ) : (
        PROVIDER_LABEL[provider]
      )}
    </span>
  );
}

// ---- Confidence meter ----

export function Confidence({ value, showLabel = true }: { value: number; showLabel?: boolean }) {
  const v = Math.max(0, Math.min(1, value));
  const tone = v >= 0.85 ? "bg-good" : v >= 0.7 ? "bg-brand-400" : "bg-warn";
  return (
    <span
      className="inline-flex items-center gap-2"
      title={`Agent confidence ${Math.round(v * 100)}%`}
    >
      <span
        className="h-1.5 w-12 overflow-hidden rounded-full bg-line"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(v * 100)}
        aria-label="Agent confidence"
      >
        <span
          className={clsx("block h-full rounded-full", tone)}
          style={{ width: `${v * 100}%` }}
        />
      </span>
      {showLabel ? <span className="tnum text-xs text-ink-3">{Math.round(v * 100)}%</span> : null}
    </span>
  );
}

// ---- States ----

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-line/70", className)} aria-hidden />;
}

export function LoadingBlock({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="space-y-3 p-5" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={clsx("h-4", i % 3 === 2 ? "w-2/3" : "w-full")} />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-col items-center px-6 py-10 text-center", className)}>
      <span className="grid size-11 place-items-center rounded-full border border-line bg-sunken">
        <Icon className="size-5 text-ink-3" aria-hidden />
      </span>
      <p className="mt-3 text-sm font-medium text-ink">{title}</p>
      {body ? <p className="mt-1 max-w-sm text-[13px] text-ink-3">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const msg = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div
      role="alert"
      className={clsx("flex flex-col items-center px-6 py-10 text-center", className)}
    >
      <span className="grid size-11 place-items-center rounded-full border border-high/20 bg-high-bg">
        <CircleAlert className="size-5 text-high" aria-hidden />
      </span>
      <p className="mt-3 text-sm font-medium text-ink">Couldn't load this</p>
      <p className="mt-1 max-w-sm text-[13px] text-ink-3">{msg}</p>
      {onRetry ? (
        <Button className="mt-4" size="sm" icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-ink-3">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line-strong bg-surface px-1.5 py-px font-mono text-[11px] text-ink-3">
      {children}
    </kbd>
  );
}
