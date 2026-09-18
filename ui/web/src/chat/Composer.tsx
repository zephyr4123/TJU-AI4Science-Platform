// 输入框就是门：还没有对话时在这里打字回车就开一段。壳是 reactbits 的 GlassSurface（浮在配图与滚过的对话上），分两层：
// 上面写字（起步三行高，随内容长到十行），下面一排是工具位——左边以后放模型切换、思考深度、上传，现在只站着快捷键提示；右边发送键。
// 宽度与正文同一列（主人：矮胖显窄，要高一点瘦一点、大气一点）。空着的时候 RotatingText 轮换提示能说什么（减少动效时静态一句）；
// 助理答着的时候只剩「助理回答中」、不许发。
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

const LINE = 24
const MIN_LINES = 3
const MAX_LINES = 10

export function Composer({ busy, hints, onSend }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const still = useReducedMotion()

  // 输入框随内容长高：起步三行，封顶十行；不用第三方 autosize
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_LINES * LINE), MAX_LINES * LINE)}px`
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
    <div className="relative z-10 px-6 pt-2 pb-5">
      <GlassSurface borderRadius={24} className="mx-auto max-w-[44rem] focus-within:ring-3 focus-within:ring-ring/35">
        <div className="relative flex flex-col px-4 pt-4 pb-3">
          {text === '' && (
            <span aria-hidden="true"
                  className="pointer-events-none absolute top-4 left-5 text-[1rem] leading-6 text-muted-foreground">
              {still
                ? texts[0]
                : <RotatingText key={texts.join('|')} texts={texts} rotationInterval={3400} staggerDuration={0.02}
                                splitBy="characters" mainClassName="overflow-hidden" />}
            </span>
          )}
          <Textarea
            ref={ref}
            value={text}
            rows={MIN_LINES}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="给助理的消息"
            className="min-h-[4.5rem] resize-none border-0 bg-transparent px-1 py-0 text-[1rem] leading-6 shadow-none focus-visible:ring-0"
          />
          <div className="mt-3 flex items-center gap-2">
            {/* 工具位：模型切换、思考深度、上传以后从左边排进来 */}
            <div className="flex min-w-0 flex-1 items-center gap-1.5 px-1">
              <span className="t-label truncate">Enter 发送，Shift + Enter 换行</span>
            </div>
            <Button size="icon-lg" className="rounded-full" onClick={submit} disabled={busy || !text.trim()} aria-label="发送">
              <ArrowUp weight="bold" className="size-5" />
            </Button>
          </div>
        </div>
      </GlassSurface>
    </div>
  )
}
