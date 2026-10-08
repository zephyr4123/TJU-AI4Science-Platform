// 输入框就是门：还没有对话时在这里打字回车就开一段。壳是 reactbits 的 GlassSurface（浮在配图与滚过的对话上），分两层：
// 上面写字（起步三行高，随内容长到十行），下面一排是工具位——左边空着留给以后（上传之类），右边发送键。哪家、模型、
// 思考深度只在设置里改（外层 #257，主人 2026-10-06：输入框上三枚片太乱，位置要留给别的）。
// 宽度与正文同一列（主人：矮胖显窄，要高一点瘦一点、大气一点）。空着的时候 placeholder 只写快捷键（主人：轮换的提示语没有信息量，删）；
// 助理答着的时候 placeholder 是那个英文词（thinking…）、不许发。
// 两种样子（外层 #257，主人 2026-10-06：像 Claude，分清主次）：还没对话时摆在正中的是上面说的大框；对话里沉在底下的（`docked`）
// 是扁长一条——起步一行、发送键在行尾，底下一句淡字「AAAI4S 是 AI，也可能会犯错。」。
import { ArrowUp } from '@phosphor-icons/react'
import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from 'react'

import { BRAND } from '@/brand'
import GlassSurface from '@/components/reactbits/GlassSurface'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { composing } from '@/lib/browser'
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
  /** 沉在对话底下：扁长一条、底下一句提醒；不给是正中那只大框 */
  docked?: boolean
  className?: string
}

const LINE = 24
// 起步几行、封顶几行：正中的大框三到十行，沉在底下的一到八行
const LINES = { open: [3, 10], docked: [1, 8] } as const

export function Composer({ busy, thinking, onSend, placeholder = 'Enter 发送，Shift + Enter 换行', above, docked = false, className }: Props) {
  const [minLines, maxLines] = LINES[docked ? 'docked' : 'open']
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  // 输入框随内容长高：从起步的行数长到封顶；不用第三方 autosize
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minLines * LINE), maxLines * LINE)}px`
  }, [text, minLines, maxLines])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    onSend(trimmed)
    setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 中文输入法组词时的回车是选词，不是发送
    if (event.key === 'Enter' && !event.shiftKey && !composing(event.nativeEvent)) {
      event.preventDefault()
      submit()
    }
  }

  const field = (
    <Textarea
      ref={ref}
      value={text}
      rows={minLines}
      onChange={(event) => setText(event.target.value)}
      onKeyDown={onKeyDown}
      aria-label="给助理的消息"
      placeholder={busy ? `${thinking}…` : placeholder}
      className={cn('resize-none border-0 bg-transparent px-1 py-0 text-[1rem] leading-6 shadow-none placeholder:text-muted-foreground focus-visible:ring-0',
                    docked ? 'my-1.5 min-h-6 flex-1' : 'min-h-[4.5rem]')}
    />
  )
  const send = (size: 'icon' | 'icon-lg') => (
    <Button size={size} className={cn('shrink-0 rounded-full', size === 'icon' && 'size-9')} onClick={submit} disabled={busy || !text.trim()} aria-label="发送">
      <ArrowUp weight="bold" className={size === 'icon' ? 'size-[1.125rem]' : 'size-5'} />
    </Button>
  )

  return (
    <div className={cn('relative z-10 px-6', docked ? 'pt-3 pb-3' : 'pt-3 pb-6', className)}>
      {above}
      <GlassSurface borderRadius={docked ? 22 : 24} className="mx-auto max-w-[44rem] focus-within:ring-3 focus-within:ring-ring/35">
        {docked
          ? <div className="flex w-full items-end gap-2 py-2 pr-2 pl-4">{field}{send('icon')}</div>
          : (
            <div className="relative flex flex-col px-4 pt-4 pb-3">
              {field}
              <div className="mt-3 flex items-center gap-2">
                {/* 工具位：空着，留给以后（上传之类） */}
                <div className="min-w-0 flex-1" />
                {send('icon-lg')}
              </div>
            </div>
          )}
      </GlassSurface>
      {docked && <p className="mt-2 text-center text-[0.75rem] text-muted-foreground">{BRAND.name} 是 AI，也可能会犯错。</p>}
    </div>
  )
}
