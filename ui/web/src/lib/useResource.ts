// 「取一份数据、可以重取」的最小封装：看板全是读盘数据，改动后 reload 一次即可，不值得上缓存库。

import { useCallback, useEffect, useRef, useState } from 'react'

export interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => Promise<void>
}

export function useResource<T>(loader: () => Promise<T>, deps: readonly unknown[]): Resource<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  // 快速切换目标时，先发出去、后回来的旧响应不能盖住新的
  const ticket = useRef(0)

  const reload = useCallback(async () => {
    const mine = ++ticket.current
    setLoading(true)
    try {
      const found = await loader()
      if (mine === ticket.current) {
        setData(found)
        setError(null)
      }
    } catch (exc) {
      if (mine === ticket.current) setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      if (mine === ticket.current) setLoading(false)
    }
    // deps 由调用方给：loader 是闭包，按它的输入重取，不按函数身份
  }, deps)

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, error, loading, reload }
}
