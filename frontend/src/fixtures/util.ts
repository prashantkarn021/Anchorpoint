// Small deterministic helpers for building fixture data relative to "today".

const DAY_MS = 86_400_000;

export function utcToday(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

export function addDays(d: Date, days: number): Date {
  return new Date(d.getTime() + days * DAY_MS);
}

/** First-of-month `n` months before `d`, plus `day - 1` days. */
export function monthsAgo(d: Date, n: number, day = 1): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - n, day));
}

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function isoDateTime(d: Date, hour = 9, minute = 0): string {
  const t = new Date(d.getTime());
  t.setUTCHours(hour, minute, 0, 0);
  return t.toISOString();
}

export function monthKey(d: Date): string {
  return d.toISOString().slice(0, 7);
}

/** Deterministic 64-hex "sha256-looking" string (fixtures only; the backend computes real hashes). */
export function fakeHash(input: string): string {
  let out = "";
  let h = 2166136261;
  for (let round = 0; round < 8; round++) {
    for (let i = 0; i < input.length; i++) {
      h ^= input.charCodeAt(i) + round;
      h = Math.imul(h, 16777619) >>> 0;
    }
    out += h.toString(16).padStart(8, "0");
  }
  return out;
}
