// 「取一份数据、可以重取」的最小封装：看板全是读盘数据，改动后 reload 一次即可，不值得上缓存库。
// 给了名字（key）的，上次拿到的那份记在 lib/lastSeen 里：再来先摆上次的，后台重拉——换地方不闪骨架屏。

import { useCallback, useEffect, useRef, useState } from 'react'

import { keep, recall } from './lastSeen'

export interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => Promise<void>
}

interface Fetched<T> { key: string | undefined; data: T | null; error: string | null }

export function useResource<T>(loader: () => Promise<T>, deps: readonly unknown[], key?: string): Resource<T> {
  // 拿到的那份跟着名字走：名字换了（同一个组件换了路径）就不拿上一个名字的顶着，改摆新名字上次那份
  const [fetched, setFetched] = useState<Fetched<T>>(() => ({ key, data: recall<T>(key), error: null }))
  const [loading, setLoading] = useState(true)
  // 快速切换目标时，先发出去、后回来的旧响应不能盖住新的
  const ticket = useRef(0)

  const reload = useCallback(async () => {
    const mine = ++ticket.current
    setLoading(true)
    try {
      const found = await loader()
      if (mine === ticket.current) {
        keep(key, found)
        setFetched({ key, data: found, error: null })
      }
    } catch (exc) {
      if (mine === ticket.current) {
        setFetched((prev) => ({ key, data: prev.key === key ? prev.data : recall<T>(key),
                                error: exc instanceof Error ? exc.message : String(exc) }))
      }
    } finally {
      if (mine === ticket.current) setLoading(false)
    }
    // deps 由调用方给：loader 是闭包，按它的输入重取，不按函数身份
  }, deps)

  useEffect(() => {
    void reload()
  }, [reload])

  const mine = fetched.key === key
  return { data: mine ? fetched.data : recall<T>(key), error: mine ? fetched.error : null, loading, reload }
}
