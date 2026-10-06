// 一块在自己里面滚的面：上下边哪头还有没露出来的，那头渐隐一截（外层 #256：首页的项目清单、花费的几张表）。
// 量的时机：滚动、面的大小变了、`content` 变了（换了内容，面不变大小也要重量）。
import { type UIEvent, useEffect, useRef, useState } from 'react'

interface Edges { above: boolean; below: boolean }

export function useEdgeFade<T extends HTMLElement>(content: unknown) {
  const ref = useRef<T>(null)
  const [edges, setEdges] = useState<Edges>({ above: false, below: false })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(() => setEdges(edgesOf(el)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [content])
  return {
    ref,
    onScroll: (e: UIEvent<T>) => setEdges(edgesOf(e.currentTarget)),
    style: { maskImage: fadeMask(edges) },
  }
}

function edgesOf(el: HTMLElement): Edges {
  return { above: el.scrollTop > 1, below: el.scrollTop + el.clientHeight < el.scrollHeight - 1 }
}

/** 哪头还有内容，那头 28px 渐隐；两头都到底就不遮 */
function fadeMask({ above, below }: Edges): string | undefined {
  if (!above && !below) return undefined
  return `linear-gradient(to bottom, ${above ? 'transparent 0, #000 28px' : '#000 0'}, ${below ? '#000 calc(100% - 28px), transparent 100%' : '#000 100%'})`
}
