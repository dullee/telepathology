import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type CaseDetail, type Region } from '../api.ts'
import { SlideViewer } from '../components/SlideViewer.tsx'
import { StatusLabel, TIER_STYLE, TierBadge } from '../components/UrgencyBadge.tsx'
import { parseDate, pct, timeAgo } from '../lib/format.ts'
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
