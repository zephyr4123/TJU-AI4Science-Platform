// 输入框就是门：还没有对话时在这里打字回车就开一段。壳是 reactbits 的 GlassSurface（浮在配图与滚过的对话上），分两层：
// 上面写字（起步三行高，随内容长到十行），下面一排是工具位——左边两枚下拉片「模型」「思考」（reactbits GlideSelect 改装，
// 清单是后端自报的，选了随下一条消息发出去、记进对话；外层 #86），还没开对话时前面多一枚「助理」选哪家（P-25：一段对话的
// 记忆存在那家手里，进了对话就不能换），上传以后排在它们后面；右边发送键。
// 宽度与正文同一列（主人：矮胖显窄，要高一点瘦一点、大气一点）。空着的时候 placeholder 只写快捷键（主人：轮换的提示语没有信息量，删）；
// 助理答着的时候 placeholder 是那个英文词（thinking…）、不许发。
import { ArrowUp } from '@phosphor-icons/react'
import { type KeyboardEvent, useEffect, useRef, useState } from 'react'

import type { Backend, Choice, Tuning } from '@/api/types'
import GlassSurface from '@/components/reactbits/GlassSurface'
import GlideSelect from '@/components/reactbits/GlideSelect'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { shownValue } from '@/lib/tuning'

interface Props {
  busy: boolean
  /** 助理想着时那个词（随选的深度变），忙着时写在 placeholder 里 */
  thinking: string
  /** 这家的两个旋钮清单与新对话用的值；还没拿到就先不摆 */
  knobs: Backend | null
  /** 这段对话记着的选；null 是这家新对话用的值 */
  tuning: Tuning
  onTune: (next: Tuning) => void
  onSend: (text: string) => void
  /** 还没开对话：选哪家助理（清单、当前、改） */
  who?: { options: Backend[]; value: string; onChange: (name: string) => void }
}

const LINE = 24
const MIN_LINES = 3
const MAX_LINES = 10

export function Composer({ busy, thinking, knobs, tuning, onTune, onSend, who }: Props) {
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
    <div className="relative z-10 px-6 pt-3 pb-6">
      <GlassSurface borderRadius={24} className="mx-auto max-w-[44rem] focus-within:ring-3 focus-within:ring-ring/35">
        <div className="relative flex flex-col px-4 pt-4 pb-3">
          <Textarea
            ref={ref}
            value={text}
            rows={MIN_LINES}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="给助理的消息"
            placeholder={busy ? `${thinking}…` : 'Enter 发送，Shift + Enter 换行'}
            className="min-h-[4.5rem] resize-none border-0 bg-transparent px-1 py-0 text-[1rem] leading-6 shadow-none placeholder:text-muted-foreground focus-visible:ring-0"
          />
          <div className="mt-3 flex items-center gap-2">
            {/* 工具位：两枚旋钮在左，上传以后排在它们后面 */}
            {/* 三枚片一行排到底、不折行（主人 2026-09-22）；板是 30rem 的，三枚放得下 */}
            <div className="flex min-w-0 flex-1 items-center gap-1.5 whitespace-nowrap">
              {who && who.options.length > 0 && (
                <GlideSelect prefix="助理" ariaLabel="哪家助理" disabled={busy} value={who.value} className="shrink-0 whitespace-nowrap"
                             options={who.options.map((b) => ({ value: b.name, label: b.title }))}
                             onChange={(name) => who.onChange(name)} />
              )}
              {knobs && (
                <>
                  <Knob prefix="模型" ariaLabel="模型" choices={knobs.models} fallback={knobs.model}
                        value={tuning.model} disabled={busy} onChange={(model) => onTune({ ...tuning, model })} />
                  <Knob prefix="思考" ariaLabel="思考深度" choices={knobs.efforts} fallback={knobs.effort}
                        value={tuning.effort} disabled={busy} onChange={(effort) => onTune({ ...tuning, effort })} />
                </>
              )}
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

interface KnobProps {
  prefix: string
  ariaLabel: string
  choices: Choice[]
  /** 这家新对话用的值（按人的设置）：还没改过就显示它 */
  fallback: string
  value: string | null
  disabled: boolean
  onChange: (value: string) => void
}

/** 一枚旋钮：清单空着（这家换不了）就不出现。片上显示记着的，或这家新对话用的值——只有具体值（P-25）。 */
function Knob({ prefix, ariaLabel, choices, fallback, value, disabled, onChange }: KnobProps) {
  if (choices.length === 0) return null
  const options = choices.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))
  return (
    <GlideSelect prefix={prefix} ariaLabel={ariaLabel} options={options} value={shownValue(value, fallback)}
                 disabled={disabled} onChange={onChange} className="shrink-0 whitespace-nowrap" />
  )
}
