/**
 * Server timestamps.
 *
 * The API sends two shapes. Trajectory and event timestamps are written with
 * ``datetime.now(timezone.utc).isoformat()`` and carry ``+00:00``; the database
 * columns are UTC too, but SQLite drops the tzinfo, so they arrive bare
 * (``2026-09-08T02:10:59.496163``). A bare date-TIME is parsed as LOCAL by
 * ``new Date``, which silently shifts every database timestamp by the reader's
 * offset — seven hours here, enough to put a run on the wrong day and defeat
 * the point of showing the time at all.
 */

/** Parse a server timestamp, reading a bare one as the UTC it actually is. */
export function parseServerTime(value: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

const RUN_STAMP = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/**
 * A run's time, short enough for a dropdown row.
 *
 * No year and no seconds: this label exists to tell one of a handful of runs
 * from another, and the id beside it is what identifies one exactly.
 */
export function runStamp(value: string | undefined): string {
  if (!value) return 'no timestamp'
  const at = parseServerTime(value)
  return Number.isNaN(at.getTime()) ? 'no timestamp' : RUN_STAMP.format(at)
}
