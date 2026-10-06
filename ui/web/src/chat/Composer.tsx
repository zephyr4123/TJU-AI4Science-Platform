// 输入框就是门：还没有对话时在这里打字回车就开一段。壳是 reactbits 的 GlassSurface（浮在配图与滚过的对话上），分两层：
// 上面写字（起步三行高，随内容长到十行），下面一排是工具位——左边空着留给以后（上传之类），右边发送键。哪家、模型、
// 思考深度只在设置里改（外层 #257，主人 2026-10-06：输入框上三枚片太乱，位置要留给别的）。
// 宽度与正文同一列（主人：矮胖显窄，要高一点瘦一点、大气一点）。空着的时候 placeholder 只写快捷键（主人：轮换的提示语没有信息量，删）；
// 助理答着的时候 placeholder 是那个英文词（thinking…）、不许发。
import { ArrowUp } from '@phosphor-icons/react'
import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from 'react'

import GlassSurface from '@/components/reactbits/GlassSurface'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface Props {
  busy: boolean
  /** 助理想着时那个词（随这段对话的思考深度变），忙着时写在 placeholder 里 */
  thinking: string
  onSend: (text: string) => void
  /** 空着时的提示；项目页正中间那只写「要做什么？」 */
  placeholder?: string
  /** 摆在输入框正上方的一条（对话底部的「运行中」，外层 #243） */
  above?: ReactNode
  className?: string
}

const LINE = 24
const MIN_LINES = 3
const MAX_LINES = 10

export function Composer({ busy, thinking, onSend, placeholder = 'Enter 发送，Shift + Enter 换行', above, className }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

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

  return (
    <div className={cn('relative z-10 px-6 pt-3 pb-6', className)}>
      {above}
      <GlassSurface borderRadius={24} className="mx-auto max-w-[44rem] focus-within:ring-3 focus-within:ring-ring/35">
        <div className="relative flex flex-col px-4 pt-4 pb-3">
          <Textarea
            ref={ref}
            value={text}
            rows={MIN_LINES}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="给助理的消息"
            placeholder={busy ? `${thinking}…` : placeholder}
            className="min-h-[4.5rem] resize-none border-0 bg-transparent px-1 py-0 text-[1rem] leading-6 shadow-none placeholder:text-muted-foreground focus-visible:ring-0"
          />
          <div className="mt-3 flex items-center gap-2">
            {/* 工具位：空着，留给以后（上传之类） */}
            <div className="min-w-0 flex-1" />
            <Button size="icon-lg" className="rounded-full" onClick={submit} disabled={busy || !text.trim()} aria-label="发送">
              <ArrowUp weight="bold" className="size-5" />
            </Button>
          </div>
        </div>
      </GlassSurface>
    </div>
  )
}
