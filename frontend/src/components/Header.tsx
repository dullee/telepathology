import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type Health } from '../api.ts'
import { usePolling } from '../lib/usePolling.ts'

export function Header() {
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  usePolling(() => {
    api.health().then(
      (h) => {
        setHealth(h)
        setOffline(false)
      },
      () => setOffline(true),
    )
  }, 15000)

  const dot = offline ? 'bg-red-500' : health?.model_ready ? 'bg-emerald-500' : 'bg-amber-400 animate-pulse'
  const label = offline
    ? 'Engine offline'
    : !health
      ? 'Connecting…'
      : health.model_ready
        ? `Edge engine · ${health.device}`
        : health.model_error
          ? 'Model failed to load'
          : `Loading model · ${health.device}`

  return (
    <header className="sticky top-0 z-[1000] border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span>PathTriage</span>
          <span className="hidden text-sm font-normal text-slate-500 sm:inline">Edge telepathology</span>
        </Link>
        <div
          className="ml-auto flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300"
          title={health?.model_error || health?.model}
        >
          <span className={`size-2 rounded-full ${dot}`} />
          <span className="max-w-[46vw] truncate">{label}</span>
        </div>
      </div>
    </header>
  )
}
