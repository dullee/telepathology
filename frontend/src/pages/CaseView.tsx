import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type CaseDetail, type CellSummary, type QualityReport, type Region } from '../api.ts'
import { SlideViewer } from '../components/SlideViewer.tsx'
import { StatusLabel, TIER_STYLE, TierBadge } from '../components/UrgencyBadge.tsx'
import { parseDate, pct, timeAgo } from '../lib/format.ts'
import { NUCLEUS_TYPES } from '../lib/nuclei.ts'
import { usePolling } from '../lib/usePolling.ts'

// Colorectal labels for results saved before models carried their own class_labels.
const KATHER_LABELS: Record<string, string> = {
  TUM: 'Tumor epithelium',
  DEB: 'Debris / necrosis',
  NORM: 'Normal mucosa',
  STR: 'Stroma',
  MUS: 'Smooth muscle',
  LYM: 'Lymphocytes',
  MUC: 'Mucus',
}

const CLASS_COLOR: Record<string, string> = {
  TUM: 'bg-red-600',
  ACA: 'bg-red-600',
  SCC: 'bg-fuchsia-700',
  DEB: 'bg-orange-500',
  NEC: 'bg-orange-500',
  NORM: 'bg-emerald-500',
  NOR: 'bg-emerald-500',
  STR: 'bg-pink-400',
  FIB: 'bg-pink-400',
  MUS: 'bg-rose-300',
  LYM: 'bg-indigo-500',
  INF: 'bg-indigo-500',
  MUC: 'bg-sky-400',
  ADI: 'bg-yellow-200',
  STE: 'bg-yellow-300',
  REA: 'bg-teal-500',
}

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
  const [focus, setFocus] = useState<Region | null>(null)

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
  const classLabels = r?.class_labels ?? KATHER_LABELS
  const classColor = (k: string) => CLASS_COLOR[k] ?? 'bg-slate-400'
  return (
    <main className="grid flex-1 lg:h-[calc(100vh-3.5rem)] lg:grid-cols-[1fr_380px]">
      <section className="relative h-[60vh] min-h-80 bg-slate-950 lg:h-auto">
        {r && c.image_url ? (
          <SlideViewer
            imageUrl={c.image_url}
            heatmapUrl={c.heatmap_url}
            width={r.width}
            height={r.height}
            regions={r.regions}
            focus={focus}
            onSelect={setFocus}
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
              onForce={() => api.reanalyze(c.id, true).then(setCase)}
            />
          )}

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
                  Triage aid only — the specialist makes the diagnosis. {r.model_label ?? 'ResNet-18 · Kather100k'} ·{' '}
                  {r.tiles} tiles · {r.device} · {(r.elapsed_ms / 1000).toFixed(1)} s ·{' '}
                  <button
                    onClick={() => api.reanalyze(c.id).then(setCase)}
                    className="text-cyan-700 hover:underline dark:text-cyan-400"
                    title="Run again with the model currently selected in the header"
                  >
                    Re-analyze
                  </button>
                </p>
              </div>

              <section>
                <h2 className="mb-2 text-sm font-semibold">Suspicious regions</h2>
                {r.regions.length === 0 ? (
                  <p className="text-sm text-slate-500">No region above the tumor threshold.</p>
                ) : (
                  <ul className="space-y-1">
                    {r.regions.map((reg) => (
                      <li key={reg.id}>
                        <button
                          onClick={() => setFocus(reg)}
                          className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition ${
                            focus?.id === reg.id
                              ? 'bg-cyan-700 text-white'
                              : 'bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800'
                          }`}
                        >
                          <span className="font-medium">Region {reg.id}</span>
                          <span className="tabular-nums opacity-80">
                            peak {pct(reg.max_prob)} · {pct(reg.area_fraction, 1)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <h2 className="mb-2 text-sm font-semibold">Tissue composition</h2>
                <div className="mb-2 flex h-3 overflow-hidden rounded-full">
                  {Object.entries(r.composition).map(([k, v]) => (
                    <div key={k} className={classColor(k)} style={{ width: `${v * 100}%` }} title={classLabels[k] ?? k} />
                  ))}
                </div>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                  {Object.entries(r.composition)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <li key={k} className="flex items-center gap-1.5">
                        <span className={`size-2 shrink-0 rounded-sm ${classColor(k)}`} />
                        <span className="flex-1 truncate text-slate-600 dark:text-slate-300" title={classLabels[k] ?? k}>
                          {classLabels[k] ?? k}
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

const QUALITY_ICON = { pass: '✓', warn: '!', reject: '✕' } as const
const QUALITY_TONE = {
  pass: 'text-emerald-600 dark:text-emerald-400',
  warn: 'text-amber-600 dark:text-amber-400',
  reject: 'text-red-600 dark:text-red-400',
} as const

/** Pre-analysis photo checks: why a photo needs retaking, or what to keep in mind about the result. */
function QualityPanel({ q, retake, onForce }: { q: QualityReport; retake: boolean; onForce: () => void }) {
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
      {retake && (
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
