// 需求（纲领 P-19）：工作区的根。没确认时它就是主页面——文档按二级标题一格一格铺开（模板留的「待填」是空格子），
// 底下一颗「确认」；确认了收成顶部一条（版本、谁、何时），点开侧滑看全文；助理又改了就显示 diff 与「确认下一版」。
// 页面只渲染不编辑：改需求只走对话（一个文件一个生产者），diff 才有意义。
import { ArrowsClockwise, CaretRight, CheckCircle, Circle } from '@phosphor-icons/react'
import { useState } from 'react'

import type { RequirementDetail, RequirementSection } from '@/api/types'
import { Markdown } from '@/components/Markdown'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ConfirmKey } from '@/keys/ConfirmKey'
import { changedCount, diffLines } from '@/lib/diff'
import { when } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 二级标题之前的引言（模板开头那段说明） */
function preface(text: string): string {
  const at = text.search(/^##\s/m)
  const head = (at < 0 ? text : text.slice(0, at)).replace(/^#\s.*$/m, '').trim()
  return head
}

// ── 未确认：需求就是页面 ────────────────────────────────────────────────────
export function RequirementPage({ workspace, requirement, reload }: {
  workspace: string; requirement: RequirementDetail; reload: () => Promise<void>
}) {
  const intro = preface(requirement.text)
  const filled = requirement.sections.filter((s) => !s.pending).length
  return (
    <div className="mx-auto w-full max-w-[64rem] px-6 pt-8 pb-16 sm:px-8">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-serif text-[2rem] leading-[1.2] font-semibold tracking-tight text-balance">{requirement.title}</h1>
        <span className="t-label whitespace-nowrap">
          需求 · 未确认{requirement.sections.length > 0 && ` · ${filled} / ${requirement.sections.length}`}
        </span>
      </header>
      {intro && <div className="mt-4 max-w-[68ch] text-[0.9375rem] leading-[1.65] text-muted-foreground"><Markdown text={intro} /></div>}
      {requirement.sections.length === 0 && (
        <p className="t-body mt-8 text-muted-foreground">尚无内容。与右侧助理说明课题，由它按模板填写。</p>
      )}
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {requirement.sections.map((section) => <SectionCard key={section.heading} section={section} />)}
      </div>
      <div className="mt-10 max-w-[36rem]">
        <ConfirmKey workspace={workspace} requirement={requirement} reload={reload} />
      </div>
    </div>
  )
}

/** 一格：标题宋体，正文 markdown；空着或「待填」的格虚线框、灰字。 */
function SectionCard({ section }: { section: RequirementSection }) {
  if (section.pending) {
    return (
      <div className="rounded-2xl border border-dashed border-border px-5 py-4 text-muted-foreground">
        <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold"><Circle className="size-4" aria-hidden />{section.heading}</h2>
        <p className="mt-2 text-[0.875rem]">待填</p>
      </div>
    )
  }
  return (
    <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 12%, transparent)" className="rounded-2xl">
      <div className="px-5 py-4">
        <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold"><CheckCircle weight="duotone" className="size-4 text-primary" aria-hidden />{section.heading}</h2>
        <div className="mt-2"><Markdown text={section.body} className="prose-p:text-[0.9rem]" /></div>
      </div>
    </SpotlightCard>
  )
}

// ── 已确认：收成一条，点开侧滑 ──────────────────────────────────────────────
export function RequirementStrip({ workspace, requirement, reload }: {
  workspace: string; requirement: RequirementDetail; reload: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const changed = requirement.dirty && requirement.confirmed_text !== null
    ? changedCount(diffLines(requirement.confirmed_text, requirement.text)) : 0
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}
              className={cn('flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-ring',
                            requirement.dirty ? 'border-wait/50 bg-wait-soft/60' : 'bg-card/80 backdrop-blur-sm')}>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-serif text-[1rem] font-semibold">{requirement.title}</span>
          <span className="mt-0.5 block truncate text-[0.8125rem] text-muted-foreground">
            需求 v{requirement.version} · {requirement.by} · {when(requirement.at)}
            {requirement.dirty && <span className="ml-2 text-wait">{changed} 行改动 · 待确认</span>}
          </span>
        </span>
        {requirement.dirty
          ? <ArrowsClockwise weight="bold" className="size-4 shrink-0 text-wait" aria-hidden />
          : <CaretRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
      </button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[40rem] data-[side=right]:sm:max-w-[40rem]">
          <SheetHeader className="px-6 pt-6 pb-2">
            <SheetTitle className="font-serif text-[1.25rem]">{requirement.title}</SheetTitle>
            <p className="t-label">v{requirement.version} · {requirement.by} · {when(requirement.at)}</p>
          </SheetHeader>
          <div className="px-6 pb-8">
            {requirement.dirty && requirement.confirmed_text !== null ? (
              <>
                <DiffView before={requirement.confirmed_text} after={requirement.text} />
                <div className="mt-6"><ConfirmKey workspace={workspace} requirement={requirement} reload={reload} compact /></div>
              </>
            ) : (
              <Markdown text={requirement.text} />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

/** 上一版确认时的原文对现在的文件：加的绿、删的红，没改的原样。 */
export function DiffView({ before, after }: { before: string; after: string }) {
  const ops = diffLines(before, after)
  return (
    <pre className="overflow-x-auto rounded-xl border bg-card p-4 font-mono text-[0.75rem] leading-[1.6] whitespace-pre-wrap" aria-label="改动">
      {ops.map((op, i) => (
        <span key={i} className={cn('block px-1', op.kind === 'added' && 'bg-ok-soft text-ok', op.kind === 'removed' && 'bg-bad-soft text-bad line-through')}>
          {op.kind === 'added' ? '+ ' : op.kind === 'removed' ? '− ' : '  '}{op.text || ' '}
        </span>
      ))}
    </pre>
  )
}
