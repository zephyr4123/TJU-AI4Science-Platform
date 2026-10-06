// 需求（纲领 P-19）：工作区的根。没确认时它就是工作区页——文档按二级标题一格一格铺开（模板留的「待填」是空格子），
// 底下一颗「确认」；确认了收成工作区标题底下一行（第几版、何时），点开居中的玻璃悬浮窗看全文；助理又改了就显示 diff 与「确认下一版」。
// 页面只渲染不编辑：改需求只走对话（一个文件一个生产者），diff 才有意义。
import { ArrowsClockwise, CaretRight, CheckCircle, Circle, FileText } from '@phosphor-icons/react'
import { useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { RequirementDetail, RequirementSection } from '@/api/types'
import { GlassDialog, GlassTitle } from '@/components/GlassDialog'
import { Markdown } from '@/components/Markdown'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
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
  workspace: WorkspaceClient; requirement: RequirementDetail; reload: () => Promise<void>
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

// ── 已确认：收成题头底下一行，点开悬浮窗 ────────────────────────────────────
/** 工作区标题底下一行（外层 #255：需求就是这个工作区的题头，不再是一张和流程平级的卡）：「需求第 N 版 · 何时确认 · 查看全文」；
 *  助理又改了这一行变成琥珀软底「需求有 N 行改动 · 待确认」——人要做的事一眼看见。点开都是居中的玻璃悬浮窗。 */
export function RequirementLine({ workspace, requirement, reload }: {
  workspace: WorkspaceClient; requirement: RequirementDetail; reload: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const changed = requirement.dirty && requirement.confirmed_text !== null
    ? changedCount(diffLines(requirement.confirmed_text, requirement.text)) : 0
  return (
    <>
      {requirement.dirty ? (
        <button type="button" onClick={() => setOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-full bg-wait-soft px-3 py-1 text-[0.8125rem] font-semibold text-wait transition-colors hover:bg-wait-soft/70 focus-visible:outline-2 focus-visible:outline-ring">
          <ArrowsClockwise weight="bold" className="size-3.5" aria-hidden />需求有 {changed} 行改动 · 待确认<CaretRight className="size-3.5" aria-hidden />
        </button>
      ) : (
        <button type="button" onClick={() => setOpen(true)}
                className="group inline-flex flex-wrap items-center gap-x-1.5 text-[0.875rem] text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring">
          <FileText weight="duotone" className="size-4 text-foreground/55" aria-hidden />
          <span className="tabular">需求第 {requirement.version} 版 · {when(requirement.at)} 确认</span>
          <span className="inline-flex items-center gap-0.5 text-primary group-hover:underline group-hover:underline-offset-4">查看全文<CaretRight className="size-3.5" aria-hidden /></span>
        </button>
      )}
      <GlassDialog open={open} onOpenChange={setOpen}>
        <header className="flex flex-col gap-1 px-6 pt-6 pb-3">
          <GlassTitle>{requirement.title}</GlassTitle>
          <p className="t-label">需求第 {requirement.version} 版 · {when(requirement.at)} 确认</p>
        </header>
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
      </GlassDialog>
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
