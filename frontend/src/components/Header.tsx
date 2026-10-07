import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type Health } from '../api.ts'
import { usePolling } from '../lib/usePolling.ts'
import { ModelPicker } from './ModelPicker.tsx'

export function Header() {
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  const refresh = useCallback(() => {
    api.health().then(
      (h) => {
        setHealth(h)
        setOffline(false)
      },
      () => setOffline(true),
    )
  }, [])
  usePolling(refresh, 15000)

  return (
    <header className="sticky top-0 z-[1000] border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span>PathTriage</span>
          <span className="hidden text-sm font-normal text-slate-500 sm:inline">Edge telepathology</span>
        </Link>
        <ModelPicker health={health} offline={offline} onChange={refresh} />
      </div>
    </header>
  )
}
