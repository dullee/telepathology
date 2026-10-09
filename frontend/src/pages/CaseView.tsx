import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type CaseDetail, type CellSummary, type QualityReport } from '../api.ts'
import { SlideViewer } from '../components/SlideViewer.tsx'
import { StatusLabel, TIER_STYLE, TierBadge } from '../components/UrgencyBadge.tsx'
import { parseDate, pct, timeAgo } from '../lib/format.ts'
import { isDemoCase } from '../lib/demo.ts'
import { buildStops, type GuideStop } from '../lib/guide.ts'
import { NUCLEUS_TYPES } from '../lib/nuclei.ts'
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
  // Demo cases are saved results: nothing to re-run.
  const demo = isDemoCase(id!)
  const result = c?.result
  const stops = useMemo(() => (result ? buildStops(result) : []), [result])

  const pending =
    !c || c.status === 'queued' || c.status === 'analyzing' || c.result?.cells?.status === 'counting'
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
  const organ = r?.organ
  // Viewing-note label for the result's organ, else the model's own label, else the code.
  const classLabel = (k: string) => {
    const label = tissueInfo(k, organ).label
    return label !== k ? label : (r?.class_labels?.[k] ?? k)
  }
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
            classes={Object.keys(r.class_labels ?? r.composition)}
            organ={organ}
            nucleiUrl={c.nuclei_url}
            nucleiCount={r.cells?.status === 'done' ? r.cells.total : undefined}
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-3 text-slate-300">
            {c.field_urls.length > 1 ? (
              <div className="grid max-w-[80%] grid-cols-4 gap-1 opacity-60 sm:grid-cols-6">
                {c.field_urls.map((u) => (
                  <img key={u} src={u} alt="" className="aspect-square rounded object-cover" />
                ))}
              </div>
            ) : (
              <img src={c.original_url} alt="" className="max-h-[50%] max-w-[70%] rounded opacity-60" />
            )}
            {c.field_urls.length > 1 && (c.status === 'queued' || c.status === 'analyzing') && (
              <p className="text-sm text-slate-400">Stitching {c.field_urls.length} photos…</p>
            )}
            {c.status === 'failed' ? (
              <p className="text-red-400">Analysis failed: {c.error}</p>
            ) : c.status === 'retake' ? (
              <p className="max-w-md px-4 text-center text-amber-300">
                Not analysed: the photo quality is too low. Please ask the clinic to retake it.
              </p>
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
                {r?.fields && (
                  <p className="mt-1 text-xs text-slate-500">
                    Stitched from {r.fields.stitched} of {r.fields.uploaded} photos
                    {r.fields.stitched < r.fields.uploaded && (
                      <span className="text-amber-600 dark:text-amber-400">
                        {' '}· {r.fields.uploaded - r.fields.stitched} left out (blurry, dark or not overlapping)
                      </span>
                    )}
                  </p>
                )}
              </div>
              <StatusLabel status={c.status} />
            </div>
          </div>

          {c.quality && (c.quality.status !== 'pass' || c.quality.dropped.length > 0) && (
            <QualityPanel
              q={c.quality}
              retake={c.status === 'retake'}
              onForce={demo ? undefined : () => api.reanalyze(c.id, true).then(setCase)}
            />
          )}

          {c.status === 'failed' && !demo && (
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
                  Triage aid only — the specialist makes the diagnosis. {r.model_label ?? 'ResNet-18 · Kather100k'} ·{' '}
                  {r.tiles} tiles · {r.device} · {(r.elapsed_ms / 1000).toFixed(1)} s
                  {!demo && (
                    <>
                      {' '}·{' '}
                      <button
                        onClick={() => api.reanalyze(c.id).then(setCase)}
                        className="text-cyan-700 hover:underline dark:text-cyan-400"
                        title="Run again with the model currently selected in the header"
                      >
                        Re-analyze
                      </button>
                    </>
                  )}
                </p>
              </div>

              <GuideTour stops={stops} focus={focus} onSelect={setFocus} hasRegions={r.regions.length > 0} organ={organ} />

              <section>
                <h2 className="mb-2 text-sm font-semibold">Tissue composition</h2>
                <div className="mb-2 flex h-3 overflow-hidden rounded-full">
                  {Object.entries(r.composition).map(([k, v]) => (
                    <div key={k} style={{ width: `${v * 100}%`, backgroundColor: tissueInfo(k, organ).color }} title={classLabel(k)} />
                  ))}
                </div>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                  {Object.entries(r.composition)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <li key={k} className="flex items-center gap-1.5">
                        <span className="size-2 shrink-0 rounded-sm" style={{ backgroundColor: tissueInfo(k, organ).color }} />
                        <span className="flex-1 truncate text-slate-600 dark:text-slate-300" title={classLabel(k)}>
                          {classLabel(k)}
                        </span>
                        <span className="tabular-nums text-slate-500">{pct(v)}</span>
                      </li>
                    ))}
                </ul>
              </section>

              {r.cells && <CellCounts cells={r.cells} />}
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
  organ,
}: {
  stops: GuideStop[]
  focus: GuideStop | null
  onSelect: (s: GuideStop) => void
  hasRegions: boolean
  organ?: string
}) {
  const i = focus ? stops.findIndex((s) => s.key === focus.key) : -1
  const info = focus ? tissueInfo(focus.cls, organ) : null
  const normal = stops.find((s) => s.cls === 'NORM' || s.cls === 'NOR')

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
          {focus.region && normal && (
            <p className="mt-2 text-xs text-slate-500">
              Tip: jump to the {tissueInfo(normal.cls, organ).label.toLowerCase()} example to compare the two.
            </p>
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
              <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: tissueInfo(s.cls, organ).color }} />
              <span className="flex-1 truncate font-medium">{s.title}</span>
              <span className="tabular-nums opacity-80">{pct(s.prob)}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

const QUALITY_ICON = { pass: '✓', warn: '!', reject: '✕' } as const
const QUALITY_TONE = {
  pass: 'text-emerald-600 dark:text-emerald-400',
  warn: 'text-amber-600 dark:text-amber-400',
  reject: 'text-red-600 dark:text-red-400',
} as const

/** Pre-analysis photo checks: why a photo needs retaking, or what to keep in mind about the result. */
function QualityPanel({ q, retake, onForce }: { q: QualityReport; retake: boolean; onForce?: () => void }) {
  const problems = q.checks.filter((ch) => ch.status !== 'pass')
  return (
    <section
      className={`rounded-lg border p-3 text-sm ${
        q.status === 'reject'
          ? 'border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/30'
          : 'border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30'
      }`}
    >
      <h2 className="font-semibold">
        {retake ? 'Retake needed: photo quality too low' : q.forced ? 'Analysed despite low photo quality' : 'Photo quality warnings'}
      </h2>
      <ul className="mt-2 space-y-1">
        {problems.map((ch) => (
          <li key={ch.name} className="flex gap-2">
            <span className={`w-3 shrink-0 text-center font-bold ${QUALITY_TONE[ch.status]}`}>{QUALITY_ICON[ch.status]}</span>
            <span>
              <span className="font-medium">{ch.label}.</span> {ch.message}
            </span>
          </li>
        ))}
        {q.dropped.map((d) => (
          <li key={d.photo} className="flex gap-2">
            <span className={`w-3 shrink-0 text-center font-bold ${QUALITY_TONE.reject}`}>✕</span>
            <span>
              <span className="font-medium">Photo {d.photo} left out.</span> {d.reason}
            </span>
          </li>
        ))}
      </ul>
      <details className="mt-2 text-xs text-slate-600 dark:text-slate-400">
        <summary className="cursor-pointer select-none">All checks</summary>
        <ul className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5">
          {q.checks.map((ch) => (
            <li key={ch.name} className="flex items-center gap-1.5">
              <span className={`font-bold ${QUALITY_TONE[ch.status]}`}>{QUALITY_ICON[ch.status]}</span>
              {ch.label}
              <span className="ml-auto tabular-nums text-slate-500">{ch.value}</span>
            </li>
          ))}
        </ul>
      </details>
      {retake && onForce && (
        <button
          onClick={onForce}
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
        >
          Analyse anyway
        </button>
      )}
    </section>
  )
}

function CellCounts({ cells }: { cells: CellSummary }) {
  if (cells.status === 'counting') {
    return (
      <section>
        <h2 className="mb-1 text-sm font-semibold">Cell counts</h2>
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <span className="size-2 animate-pulse rounded-full bg-amber-400" />
          Counting nuclei… the urgency score above is already final.
        </p>
      </section>
    )
  }
  if (cells.status === 'failed') {
    return (
      <section>
        <h2 className="mb-1 text-sm font-semibold">Cell counts</h2>
        <p className="text-sm text-red-600">Cell counting failed: {cells.error}</p>
      </section>
    )
  }
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">Cell counts</h2>
      <dl className="mb-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-md bg-slate-50 py-2 dark:bg-slate-800/50">
          <dd className="text-lg font-semibold tabular-nums">{cells.total.toLocaleString()}</dd>
          <dt className="text-[11px] text-slate-500">nuclei</dt>
        </div>
        <div className="rounded-md bg-slate-50 py-2 dark:bg-slate-800/50">
          <dd className="text-lg font-semibold tabular-nums">{pct(cells.fractions.neoplastic)}</dd>
          <dt className="text-[11px] text-slate-500">neoplastic</dt>
        </div>
        <div className="rounded-md bg-slate-50 py-2 dark:bg-slate-800/50">
          <dd className="text-lg font-semibold tabular-nums">{Math.round(cells.per_mm2).toLocaleString()}</dd>
          <dt className="text-[11px] text-slate-500">per mm² tissue</dt>
        </div>
      </dl>
      <ul className="space-y-1 text-xs">
        {NUCLEUS_TYPES.map((t) => (
          <li key={t.key} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-slate-600 dark:text-slate-300">{t.label}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <span className={`block h-full ${t.swatch}`} style={{ width: `${(cells.fractions[t.key] ?? 0) * 100}%` }} />
            </span>
            <span className="w-12 text-right tabular-nums text-slate-500">{(cells.counts[t.key] ?? 0).toLocaleString()}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-slate-500">
        Cell types need a sharp photo: slight blur makes tumor nuclei read as connective or benign, so a low
        neoplastic % on a soft image is not reassuring. HoVer-Net (PanNuke) · assumes a 20× objective (~0.5 µm/px) ·{' '}
        {(cells.elapsed_ms / 1000).toFixed(0)} s · research use only.
      </p>
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
