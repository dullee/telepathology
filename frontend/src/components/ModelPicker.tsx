import { useEffect, useRef, useState } from 'react'

import { api, type Health, type ModelInfo, type ModelStatus } from '../api.ts'
import { usePolling } from '../lib/usePolling.ts'

const SPEED: Record<ModelInfo['speed'], string> = { fast: 'Fast', medium: 'Medium', slow: 'GPU recommended' }
const ORGAN_DOT: Record<string, string> = {
  Colorectal: 'bg-amber-500',
  Stomach: 'bg-rose-500',
  Liver: 'bg-red-800',
  Lung: 'bg-sky-500',
}

function groupByOrgan(models: ModelInfo[]): [string, ModelInfo[]][] {
  const groups = new Map<string, ModelInfo[]>()
  for (const m of models) groups.set(m.organ, [...(groups.get(m.organ) ?? []), m])
  return [...groups]
}

const pct = (v?: number) => (v == null ? '' : `${Math.round(v * 100)}%`)

function ModelRow({
  m,
  active,
  loading,
  onChoose,
}: {
  m: ModelInfo
  active: boolean
  loading: boolean
  onChoose: (m: ModelInfo) => void
}) {
  const v = m.validation
  return (
    <li>
      <button
        role="menuitemradio"
        aria-checked={active}
        disabled={!m.available || active}
        onClick={() => onChoose(m)}
        title={m.unavailable_reason || undefined}
        className={`flex w-full gap-3 px-4 py-2.5 text-left transition disabled:cursor-default ${
          active ? 'bg-cyan-50 dark:bg-cyan-950/40' : 'hover:bg-slate-50 dark:hover:bg-slate-800/60'
        } ${!m.available ? 'opacity-50' : ''}`}
      >
        <span
          className={`mt-1 size-3.5 shrink-0 rounded-full border-2 ${
            active
              ? 'border-cyan-700 bg-cyan-700 ring-2 ring-white ring-inset dark:ring-slate-900'
              : 'border-slate-300 dark:border-slate-600'
          }`}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{m.label}</span>
            {m.family === 'foundation' && (
              <span className="rounded bg-violet-600/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
                Foundation
              </span>
            )}
            {loading && <span className="text-xs text-amber-600 dark:text-amber-400">loading…</span>}
          </span>
          <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">{m.description}</span>
          {m.trained_on && <span className="mt-0.5 block text-[11px] text-slate-500">Trained on {m.trained_on}</span>}
          {v.val_accuracy_degraded != null && (
            <span className="mt-0.5 block text-[11px] text-emerald-700 dark:text-emerald-400">
              Validated: {pct(v.val_accuracy)} accuracy · {pct(v.val_accuracy_degraded)} on phone-degraded tiles
            </span>
          )}
          <span className="mt-1 block text-[11px] text-slate-500">
            {[m.params && `${m.params} params`, SPEED[m.speed], m.license].filter(Boolean).join(' · ')}
            {!m.weights_cached && m.download_gb > 0 && ` · ${m.download_gb} GB download on first use`}
          </span>
          {!m.available && (
            <span className="mt-1 block text-[11px] text-red-600 dark:text-red-400">{m.unavailable_reason}</span>
          )}
        </span>
      </button>
    </li>
  )
}

/** Engine status pill that opens a menu to switch the tile classifier. */
export function ModelPicker({ health, offline, onChange }: { health: Health | null; offline: boolean; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<ModelStatus | null>(null)
  const [error, setError] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const switching = !!status && status.loaded !== status.active && !status.error
  usePolling(
    () => api.models().then(setStatus, () => {}),
    switching ? 2000 : 15000,
    open || switching,
  )
  // Refresh the header as soon as a switch finishes loading.
  const wasSwitching = useRef(false)
  useEffect(() => {
    if (wasSwitching.current && !switching) onChange()
    wasSwitching.current = switching
  }, [switching, onChange])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  async function choose(m: ModelInfo) {
    setError('')
    try {
      setStatus(await api.setModel(m.id))
      onChange()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const ready = health?.model_ready && !switching
  const dot = offline ? 'bg-red-500' : ready ? 'bg-emerald-500' : health?.model_error ? 'bg-red-500' : 'bg-amber-400 animate-pulse'
  const label = offline
    ? 'Engine offline'
    : !health
      ? 'Connecting…'
      : health.model_error && !switching
        ? 'Model failed to load'
        : ready
          ? `${health.model_label} · ${health.device}`
          : `Loading ${health.model_label}…`

  return (
    <div ref={ref} className="relative ml-auto">
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={offline}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-100 disabled:hover:bg-transparent dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        title={health?.model_error || 'Change analysis model'}
      >
        <span className={`size-2 shrink-0 rounded-full ${dot}`} />
        <span className="max-w-[46vw] truncate">{label}</span>
        <svg viewBox="0 0 20 20" className="size-3.5 shrink-0 opacity-60" fill="currentColor" aria-hidden>
          <path d="M5.2 7.5a.75.75 0 0 1 1.06 0L10 11.2l3.74-3.7a.75.75 0 1 1 1.06 1.06l-4.27 4.25a.75.75 0 0 1-1.06 0L5.2 8.56a.75.75 0 0 1 0-1.06Z" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-[min(26rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          <div className="border-b border-slate-200 px-4 py-2.5 dark:border-slate-800">
            <p className="text-sm font-semibold">Analysis model</p>
            <p className="text-xs text-slate-500">
              Used for new uploads and re-analyses. Existing results keep the model that produced them.
            </p>
          </div>
          {!status ? (
            <p className="px-4 py-6 text-center text-sm text-slate-500">Loading models…</p>
          ) : (
            <div className="max-h-[70vh] overflow-y-auto pb-1">
              {groupByOrgan(status.models).map(([organ, models]) => (
                <section key={organ} aria-label={organ}>
                  <h3 className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-100 bg-slate-50/95 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
                    <span className={`size-2 rounded-full ${ORGAN_DOT[organ] ?? 'bg-slate-400'}`} />
                    {organ}
                  </h3>
                  <ul className="py-1">
                    {models.map((m) => (
                      <ModelRow
                        key={m.id}
                        m={m}
                        active={m.id === status.active}
                        loading={m.id === status.active && status.loaded !== m.id && !status.error}
                        onChoose={choose}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
          {(error || status?.error) && (
            <p className="border-t border-slate-200 px-4 py-2 text-xs text-red-600 dark:border-slate-800 dark:text-red-400">
              {error || status?.error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
