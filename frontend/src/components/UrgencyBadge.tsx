import type { Status, Tier } from '../api.ts'

export const TIER_STYLE: Record<Tier, { label: string; badge: string; bar: string; ring: string }> = {
  critical: {
    label: 'Critical',
    badge: 'bg-red-600 text-white',
    bar: 'bg-red-600',
    ring: 'border-l-red-600',
  },
  high: {
    label: 'High',
    badge: 'bg-amber-500 text-white dark:text-slate-950',
    bar: 'bg-amber-500',
    ring: 'border-l-amber-500',
  },
  routine: {
    label: 'Routine',
    badge: 'bg-emerald-600/15 text-emerald-700 dark:text-emerald-400',
    bar: 'bg-emerald-600',
    ring: 'border-l-emerald-600',
  },
}

export function TierBadge({ tier }: { tier: Tier | null }) {
  if (!tier) return null
  const s = TIER_STYLE[tier]
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${s.badge}`}>
      {s.label}
    </span>
  )
}

export function UrgencyBar({ value, tier }: { value: number | null; tier: Tier | null }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        {value != null && tier && (
          <div className={`h-full rounded-full ${TIER_STYLE[tier].bar}`} style={{ width: `${Math.max(3, value)}%` }} />
        )}
      </div>
      <span className="w-8 text-right font-mono text-sm tabular-nums">{value == null ? '—' : Math.round(value)}</span>
    </div>
  )
}

const STATUS_STYLE: Record<Status, string> = {
  queued: 'text-slate-500',
  analyzing: 'text-sky-600 dark:text-sky-400',
  ready: 'text-slate-700 dark:text-slate-200',
  reviewed: 'text-emerald-700 dark:text-emerald-400',
  failed: 'text-red-600',
}

const STATUS_LABEL: Record<Status, string> = {
  queued: 'Queued',
  analyzing: 'Analyzing',
  ready: 'Awaiting review',
  reviewed: 'Reviewed',
  failed: 'Analysis failed',
}

export function StatusLabel({ status }: { status: Status }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${STATUS_STYLE[status]}`}>
      {(status === 'analyzing' || status === 'queued') && (
        <span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {STATUS_LABEL[status]}
    </span>
  )
}
