// 输入框就是门：还没有对话时在这里打字回车就开一段。壳是 reactbits 的 GlassSurface（浮在配图与滚过的对话上），
// 空着的时候 RotatingText 轮换提示能说什么（减少动效时静态一句）；助理答着的时候只剩「助理回答中」、不许发。
import { ArrowUp } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type KeyboardEvent, useEffect, useRef, useState } from 'react'

import GlassSurface from '@/components/reactbits/GlassSurface'
import RotatingText from '@/components/reactbits/RotatingText'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface Props {
  busy: boolean
  /** 轮换的提示语，三句短的 */
  hints: string[]
  onSend: (text: string) => void
}

export function Composer({ busy, hints, onSend }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const still = useReducedMotion()

  // 输入框随内容长高，封顶 8 行；不用第三方 autosize
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 8 * 24 + 16)}px`
  }, [text])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    onSend(trimmed)
    setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 中文输入法组词时的回车是选词，不是发送
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const texts = busy ? ['助理回答中'] : hints
  return (
    <div className="relative z-10 px-4 pt-2 pb-3">
      <GlassSurface borderRadius={22} className="mx-auto max-w-3xl focus-within:ring-3 focus-within:ring-ring/35">
        <div className="relative flex items-end gap-2 p-2">
          {text === '' && (
            <span aria-hidden="true"
                  className="pointer-events-none absolute top-[0.875rem] left-4 text-[0.9375rem] leading-6 text-muted-foreground">
              {still
                ? texts[0]
                : <RotatingText key={texts.join('|')} texts={texts} rotationInterval={3400} staggerDuration={0.02}
                                splitBy="characters" mainClassName="overflow-hidden" />}
            </span>
          )}
          <Textarea
            ref={ref}
            value={text}
            rows={1}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="给助理的消息"
            className="min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 text-[0.9375rem] leading-6 shadow-none focus-visible:ring-0"
          />
          <Button size="icon" className="rounded-full" onClick={submit} disabled={busy || !text.trim()} aria-label="发送">
            <ArrowUp weight="bold" />
          </Button>
        </div>
      </GlassSurface>
      <p className="mx-auto mt-1.5 max-w-3xl px-1 text-xs text-muted-foreground">Enter 发送，Shift + Enter 换行</p>
    </div>
  )
}
