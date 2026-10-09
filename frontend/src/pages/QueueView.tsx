import { useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type CaseSummary, USES_LOCAL_BACKEND } from '../api.ts'
import { DemoNotice } from '../components/DemoNotice.tsx'
import { UploadPanel } from '../components/UploadPanel.tsx'
import { StatusLabel, TIER_STYLE, TierBadge, UrgencyBar } from '../components/UrgencyBadge.tsx'
import { useDemoMode } from '../lib/demo.ts'
import { pct, timeAgo } from '../lib/format.ts'
import { usePolling } from '../lib/usePolling.ts'

type Filter = 'active' | 'reviewed' | ''

/** FLIP animation: rows glide to their new position when the queue re-sorts. */
function useReorderAnimation(keys: string) {
  const rows = useRef(new Map<number, HTMLElement>())
  const last = useRef(new Map<number, number>())
  useLayoutEffect(() => {
    const next = new Map<number, number>()
    rows.current.forEach((el, id) => {
      const top = el.getBoundingClientRect().top
      next.set(id, top)
      const prev = last.current.get(id)
      if (prev != null && prev !== top) {
        el.classList.remove('reorder-move')
        el.style.transform = `translateY(${prev - top}px)`
        requestAnimationFrame(() => {
          el.classList.add('reorder-move')
          el.style.transform = ''
        })
      }
    })
    last.current = next
  }, [keys])
  return (id: number) => (el: HTMLElement | null) => {
    if (el) rows.current.set(id, el)
    else rows.current.delete(id)
  }
}

export function QueueView() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [filter, setFilter] = useState<Filter>('active')
  const [error, setError] = useState('')
  const [, setNow] = useState(Date.now())
  const demo = useDemoMode()

  const load = () =>
    api.listCases(filter).then(
      (c) => {
        setCases(c)
        setError('')
        setNow(Date.now())
      },
      (e: Error) => setError(e.message),
    )
  usePolling(load, 4000, true, [filter])

  const rowRef = useReorderAnimation((cases ?? []).map((c) => c.id).join(','))
  const counts = {
    critical: cases?.filter((c) => c.tier === 'critical' && c.status === 'ready').length ?? 0,
    high: cases?.filter((c) => c.tier === 'high' && c.status === 'ready').length ?? 0,
    pending: cases?.filter((c) => c.status === 'queued' || c.status === 'analyzing').length ?? 0,
  }

  return (
    <main className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 lg:grid-cols-[1fr_320px]">
      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Triage queue</h1>
            <p className="text-sm text-slate-500">Highest-risk cases first. Scores are an AI triage aid, not a diagnosis.</p>
          </div>
          <div className="ml-auto flex rounded-md border border-slate-200 bg-white p-0.5 text-sm dark:border-slate-800 dark:bg-slate-900">
            {(
              [
                ['active', 'Active'],
                ['reviewed', 'Reviewed'],
                ['', 'All'],
              ] as const
            ).map(([v, label]) => (
              <button
                key={v}
                onClick={() => {
                  if (v !== filter) setCases(null)
                  setFilter(v)
                }}
                className={`rounded px-3 py-1 ${filter === v ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900' : 'text-slate-600 dark:text-slate-400'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {filter === 'active' && (
          <div className="mb-4 grid grid-cols-3 gap-3">
            <Stat label="Critical" value={counts.critical} tone="text-red-600" />
            <Stat label="High" value={counts.high} tone="text-amber-600" />
            <Stat label="Analyzing" value={counts.pending} tone="text-sky-600" />
          </div>
        )}

        {demo && <DemoNotice />}

        {error && (
          <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            Can't reach the triage engine: {error}
            {USES_LOCAL_BACKEND && (
              <p className="mt-1">
                This site uses the backend on your own computer. Start it in the project folder with{' '}
                <code className="rounded bg-red-100 px-1 dark:bg-red-900/50">
                  cd backend &amp;&amp; uv run uvicorn app.main:app --port 8000
                </code>
                , then reload. Use Chrome, Edge or Firefox, and allow local network access if the browser asks.
              </p>
            )}
          </div>
        )}

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="hidden grid-cols-[110px_1fr_1fr_150px_140px] gap-3 border-b border-slate-200 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500 md:grid dark:border-slate-800">
            <span>Tier</span>
            <span>Patient</span>
            <span>Clinic</span>
            <span>Urgency</span>
            <span>Status</span>
          </div>
          {cases === null && <div className="p-8 text-center text-sm text-slate-500">Loading…</div>}
          {cases?.length === 0 && (
            <div className="p-8 text-center text-sm text-slate-500">
              {filter === 'active' ? 'No cases waiting. Upload a slide photo to begin.' : 'Nothing here yet.'}
            </div>
          )}
          <ul>
            {cases?.map((c) => (
              <li key={c.id} ref={rowRef(c.id)} className="relative bg-white dark:bg-slate-900">
                <Link
                  to={`/cases/${c.id}`}
                  className={`grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 border-b border-l-4 border-b-slate-100 px-4 py-3 transition hover:bg-slate-50 md:grid-cols-[106px_1fr_1fr_150px_140px] md:items-center dark:border-b-slate-800 dark:hover:bg-slate-800/60 ${
                    c.tier && c.status !== 'queued' && c.status !== 'analyzing' ? TIER_STYLE[c.tier].ring : 'border-l-transparent'
                  }`}
                >
                  <span className="order-2 md:order-none">
                    <TierBadge tier={c.status === 'failed' ? null : c.tier} />
                  </span>
                  <span className="order-1 min-w-0 md:order-none">
                    <span className="block truncate font-medium">{c.patient_ref}</span>
                    <span className="block truncate text-xs text-slate-500">
                      {c.specimen || 'Specimen'} · {timeAgo(c.created_at)}
                    </span>
                  </span>
                  <span className="order-3 truncate text-sm text-slate-600 md:order-none dark:text-slate-400">
                    {c.clinic || '—'}
                    {c.status === 'ready' && c.regions_count > 0 && (
                      <span className="block text-xs text-slate-500">
                        {c.regions_count} region{c.regions_count > 1 ? 's' : ''} · tumor {pct(c.tumor_fraction)}
                      </span>
                    )}
                  </span>
                  <span className="order-4 md:order-none">
                    <UrgencyBar value={c.urgency} tier={c.tier} />
                  </span>
                  <span className="order-5 col-span-2 md:order-none md:col-span-1">
                    <StatusLabel status={c.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-1 font-semibold">New case</h2>
          <p className="mb-3 text-xs text-slate-500">
            Photograph the slide through the eyepiece with the phone adapter. Analysis runs on this clinic's edge device.
          </p>
          {demo ? (
            <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
              Uploading needs the triage engine running on this computer. The demo cases in the queue show what
              comes back.
            </p>
          ) : (
            <UploadPanel onUploaded={load} />
          )}
        </div>
      </aside>
    </main>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  )
}
