import { SendHorizontal } from 'lucide-react'
import { type KeyboardEvent, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface Props {
  disabled: boolean
  busy: boolean
  onSend: (text: string) => void
}

export function Composer({ disabled, busy, onSend }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  // 输入框随内容长高，封顶 8 行；不用第三方 autosize
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 8 * 24 + 16)}px`
  }, [text])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled || busy) return
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
    <div className="border-t bg-background px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border bg-background p-2 shadow-xs transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30">
        <Textarea
          ref={ref}
          value={text}
          rows={1}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={disabled ? '先在左边开一段对话' : busy ? '助理在回答，稍等…' : '想做什么实验？数据在哪、想要什么效果'}
          aria-label="给助理的消息"
          className="min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
        />
        <Button size="icon" onClick={submit} disabled={disabled || busy || !text.trim()}
                aria-label="发送">
          <SendHorizontal />
        </Button>
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl px-1 text-xs text-muted-foreground">
        Enter 发送，Shift + Enter 换行。助理按的每个按钮都会显示在回答上方。
      </p>
    </div>
  )
}
