import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type CaseDetail } from '../api.ts'
import { SlideViewer } from '../components/SlideViewer.tsx'
import { StatusLabel, TIER_STYLE, TierBadge } from '../components/UrgencyBadge.tsx'
import { parseDate, pct, timeAgo } from '../lib/format.ts'
import { buildStops, type GuideStop } from '../lib/guide.ts'
import { tissueInfo } from '../lib/tissue.ts'
import { usePolling } from '../lib/usePolling.ts'

const DIAGNOSES = [
  'Adenocarcinoma — confirmed',
  'Suspicious — request repeat biopsy',
  'Dysplasia / adenoma',
  'Benign / inflammatory',
  'Non-diagnostic image — recapture',
]

export function CaseView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [c, setCase] = useState<CaseDetail | null>(null)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<GuideStop | null>(null)
  const result = c?.result
  const stops = useMemo(() => (result ? buildStops(result) : []), [result])

  const pending = !c || c.status === 'queued' || c.status === 'analyzing'
  usePolling(
    () => api.getCase(id!).then(setCase, (e: Error) => setError(e.message)),
    2500,
    pending,
    [id],
  )

  if (error && !c) {
    return (
      <main className="p-8 text-center">
        <p className="text-red-600">{error}</p>
        <Link to="/" className="mt-2 inline-block text-cyan-700 underline">
          Back to queue
        </Link>
      </main>
    )
  }
  if (!c) return <main className="p-8 text-center text-slate-500">Loading case…</main>

  const r = c.result
  return (
    <main className="grid flex-1 lg:h-[calc(100vh-3.5rem)] lg:grid-cols-[1fr_380px]">
      <section className="relative h-[60vh] min-h-80 bg-slate-950 lg:h-auto">
        {r && c.image_url ? (
          <SlideViewer
            imageUrl={c.image_url}
            heatmapUrl={c.heatmap_url}
            tissueMapUrl={c.tissue_map_url}
            width={r.width}
            height={r.height}
            stops={stops}
            focus={focus}
            onSelect={setFocus}
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-slate-300">
            <img src={c.original_url} alt="" className="max-h-[50%] max-w-[70%] rounded opacity-60" />
            {c.status === 'failed' ? (
              <p className="text-red-400">Analysis failed: {c.error}</p>
            ) : (
              <StatusLabel status={c.status} />
            )}
          </div>
        )}
      </section>

      <aside className="overflow-y-auto border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="space-y-5 p-5">
          <div>
            <Link to="/" className="text-sm text-cyan-700 hover:underline dark:text-cyan-400">
              ← Queue
            </Link>
            <div className="mt-2 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-xl font-semibold tracking-tight">{c.patient_ref}</h1>
                <p className="text-sm text-slate-500">
                  {[c.specimen, c.clinic].filter(Boolean).join(' · ') || 'No specimen details'}
                </p>
                <p className="text-xs text-slate-500" title={parseDate(c.created_at).toLocaleString()}>
                  Received {timeAgo(c.created_at)}
                </p>
              </div>
              <StatusLabel status={c.status} />
            </div>
          </div>

          {c.status === 'failed' && (
            <button
              onClick={() => api.reanalyze(c.id).then(setCase)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
            >
              Retry analysis
            </button>
          )}

          {r && c.tier && (
            <>
              <div className={`rounded-lg border-l-4 bg-slate-50 p-4 dark:bg-slate-800/50 ${TIER_STYLE[c.tier].ring}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">AI urgency score</span>
                  <TierBadge tier={c.tier} />
                </div>
                <div className="mt-1 text-4xl font-semibold tabular-nums">
                  {Math.round(r.urgency)}
                  <span className="text-base font-normal text-slate-400">/100</span>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  <dt className="text-slate-500">Tumor in tissue</dt>
                  <dd className="text-right tabular-nums">{pct(r.tumor_fraction)}</dd>
                  <dt className="text-slate-500">Lesion burden</dt>
                  <dd className="text-right tabular-nums">{pct(r.lesion_fraction)}</dd>
                  <dt className="text-slate-500">Peak confidence</dt>
                  <dd className="text-right tabular-nums">{pct(r.max_tumor_prob)}</dd>
                  <dt className="text-slate-500">Necrosis</dt>
                  <dd className="text-right tabular-nums">{pct(r.necrosis_fraction)}</dd>
                </dl>
                <p className="mt-3 text-xs text-slate-500">
                  Triage aid only — the specialist makes the diagnosis. {r.tiles} tiles · {r.device} ·{' '}
                  {(r.elapsed_ms / 1000).toFixed(1)} s
                </p>
              </div>

              <GuideTour stops={stops} focus={focus} onSelect={setFocus} hasRegions={r.regions.length > 0} />

              <section>
                <h2 className="mb-2 text-sm font-semibold">Tissue composition</h2>
                <div className="mb-2 flex h-3 overflow-hidden rounded-full">
                  {Object.entries(r.composition).map(([k, v]) => (
                    <div key={k} style={{ width: `${v * 100}%`, backgroundColor: tissueInfo(k).color }} title={tissueInfo(k).label} />
                  ))}
                </div>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                  {Object.entries(r.composition)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <li key={k} className="flex items-center gap-1.5">
                        <span className="size-2 rounded-sm" style={{ backgroundColor: tissueInfo(k).color }} />
                        <span className="flex-1 truncate text-slate-600 dark:text-slate-300">{tissueInfo(k).label}</span>
                        <span className="tabular-nums text-slate-500">{pct(v)}</span>
                      </li>
                    ))}
                </ul>
              </section>
            </>
          )}

          {(c.status === 'ready' || c.status === 'reviewed') && (
            <ReviewForm c={c} onSaved={(updated) => (updated.status === 'reviewed' ? navigate('/') : setCase(updated))} />
          )}
        </div>
      </aside>
    </main>
  )
}

function GuideTour({
  stops,
  focus,
  onSelect,
  hasRegions,
}: {
  stops: GuideStop[]
  focus: GuideStop | null
  onSelect: (s: GuideStop) => void
  hasRegions: boolean
}) {
  const i = focus ? stops.findIndex((s) => s.key === focus.key) : -1
  const info = focus ? tissueInfo(focus.cls) : null

  return (
    <section>
      <h2 className="text-sm font-semibold">What to look at</h2>
      <p className="mb-2 mt-0.5 text-xs text-slate-500">
        {hasRegions ? 'Numbered pins mark the most suspicious spots. ' : 'No region crossed the tumor threshold. '}
        Small dots mark reference examples of other tissue. The AI judges small squares of tissue, not single cells,
        so check the clues inside the dashed circle.
      </p>

      {focus && info ? (
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold">{focus.title}</h3>
            <span className="text-xs tabular-nums text-slate-500">
              {i + 1} of {stops.length}
            </span>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs">
            <span className="size-2.5 rounded-sm" style={{ backgroundColor: info.color }} />
            AI reads this as <strong>{info.label}</strong> · {pct(focus.prob)} confident
          </p>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{info.what}</p>
          <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Look for</h4>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-sm">
            {info.lookFor.map((clue) => (
              <li key={clue}>{clue}</li>
            ))}
          </ul>
          {focus.cls === 'TUM' && stops.some((s) => s.cls === 'NORM') && (
            <p className="mt-2 text-xs text-slate-500">Tip: jump to the normal mucosa example to compare the two.</p>
          )}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              disabled={i <= 0}
              onClick={() => onSelect(stops[i - 1])}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-slate-700"
            >
              ← Previous
            </button>
            <button
              disabled={i >= stops.length - 1}
              onClick={() => onSelect(stops[i + 1])}
              className="rounded-md bg-cyan-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-cyan-800 disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      ) : (
        stops.length > 0 && (
          <button
            onClick={() => onSelect(stops[0])}
            className="w-full rounded-md bg-cyan-700 px-3 py-2 text-sm font-semibold text-white hover:bg-cyan-800"
          >
            Start guided tour ({stops.length} stops)
          </button>
        )
      )}

      <ol className="mt-2 space-y-1">
        {stops.map((s) => (
          <li key={s.key}>
            <button
              onClick={() => onSelect(s)}
              className={`flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm transition ${
                focus?.key === s.key
                  ? 'bg-cyan-700 text-white'
                  : 'bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800'
              }`}
            >
              <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: tissueInfo(s.cls).color }} />
              <span className="flex-1 truncate font-medium">{s.title}</span>
              <span className="tabular-nums opacity-80">{pct(s.prob)}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

function ReviewForm({ c, onSaved }: { c: CaseDetail; onSaved: (c: CaseDetail) => void }) {
  const [diagnosis, setDiagnosis] = useState(c.diagnosis)
  const [notes, setNotes] = useState(c.notes)
  const [busy, setBusy] = useState(false)
  const field =
    'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900'

  async function save(status: 'reviewed' | 'ready') {
    setBusy(true)
    try {
      onSaved(await api.reviewCase(c.id, { diagnosis, notes, status }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-800">
      <h2 className="text-sm font-semibold">Specialist review</h2>
      <select className={field} value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)}>
        <option value="">Select impression…</option>
        {DIAGNOSES.map((d) => (
          <option key={d}>{d}</option>
        ))}
      </select>
      <textarea
        className={`${field} min-h-24`}
        placeholder="Report notes for the referring clinic"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {c.status === 'reviewed' ? (
        <button
          disabled={busy}
          onClick={() => save('ready')}
          className="w-full rounded-md border border-slate-300 px-4 py-2 text-sm dark:border-slate-700"
        >
          Reopen case
        </button>
      ) : (
        <button
          disabled={busy || !diagnosis}
          onClick={() => save('reviewed')}
          className="w-full rounded-md bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-cyan-800 disabled:opacity-40"
        >
          Sign out &amp; remove from queue
        </button>
      )}
    </section>
  )
}
