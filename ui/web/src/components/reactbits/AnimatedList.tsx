// 逐条浮现的清单，从 reactbits 的 AnimatedList 捞来改装（MIT，https://reactbits.dev/components/animated-list）：
// 工作区切换清单与对话抽屉用。改装点：条目由调用方渲染（不只是一行字）；不抢全局的方向键（条目本身是 button，Tab 就够）；
// 上下两道渐隐走 tokens、颜色由所在面板给；减少动效时直接出现。
import { motion, useInView, useReducedMotion } from 'motion/react'
import { type ReactNode, type UIEvent, useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

interface Props<T> {
  items: T[]
  keyOf: (item: T) => string
  render: (item: T, index: number) => ReactNode
  /** 渐隐的底色：清单在弹层里还是在抽屉里 */
  fade: 'popover' | 'background'
  className?: string
  listClassName?: string
}

export function AnimatedList<T>({ items, keyOf, render, fade, className, listClassName }: Props<T>) {
  const listRef = useRef<HTMLDivElement>(null)
  const [top, setTop] = useState(0)
  const [bottom, setBottom] = useState(0)
  const still = useReducedMotion()

  const measure = (el: HTMLDivElement) => {
    const { scrollTop, scrollHeight, clientHeight } = el
    setTop(Math.min(scrollTop / 40, 1))
    setBottom(scrollHeight <= clientHeight ? 0 : Math.min((scrollHeight - scrollTop - clientHeight) / 40, 1))
  }
  useEffect(() => { if (listRef.current) measure(listRef.current) }, [items])

  const fromColor = fade === 'popover' ? 'from-popover' : 'from-background'
  return (
    <div className={cn('relative', className)}>
      <div ref={listRef} onScroll={(e: UIEvent<HTMLDivElement>) => measure(e.currentTarget)} className={cn('overflow-y-auto', listClassName)}>
        {items.map((item, i) => (
          still
            ? <div key={keyOf(item)}>{render(item, i)}</div>
            : <Item key={keyOf(item)} index={i}>{render(item, i)}</Item>
        ))}
      </div>
      <div aria-hidden="true" style={{ opacity: top }}
           className={cn('pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b to-transparent transition-opacity', fromColor)} />
      <div aria-hidden="true" style={{ opacity: bottom }}
           className={cn('pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t to-transparent transition-opacity', fromColor)} />
    </div>
  )
}

function Item({ index, children }: { index: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { amount: 0.4, once: true })
  return (
    <motion.div ref={ref} initial={{ scale: 0.94, opacity: 0 }} animate={inView ? { scale: 1, opacity: 1 } : undefined}
                transition={{ duration: 0.2, delay: Math.min(index, 8) * 0.04 }}>
      {children}
    </motion.div>
  )
}
