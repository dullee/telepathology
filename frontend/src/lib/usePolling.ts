import { useEffect, useRef } from 'react'

/**
 * Calls `fn` now and every `ms` while `enabled`; pauses while the tab is hidden.
 * Restarts (and fires immediately) when any of `deps` change.
 */
export function usePolling(fn: () => void, ms: number, enabled = true, deps: unknown[] = []) {
  const saved = useRef(fn)
  useEffect(() => {
    saved.current = fn
  })
  useEffect(() => {
    if (!enabled) return
    const tick = () => {
      if (!document.hidden) saved.current()
    }
    tick()
    const id = setInterval(tick, ms)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, enabled, ...deps])
}
