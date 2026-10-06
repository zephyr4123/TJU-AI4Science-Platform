// 首页右半边第一行（外层 #256）：两张小卡并排——「待你确认」（需求未确认或有改动、流程停在断点）与「运行中」（作业），
// 跨项目。研究者回到首页第一件想知道的是有没有事要自己做，不用一个个点进项目。一行一件事：左边一枚带颜色的小方块说是
// 哪种（琥珀 = 等人确认，靛 = 在跑），中间工作区名与所在项目，右边一个词；点一行进那个工作区。一张卡最多露三件，
// 其余写「还有 N 件」（主人 2026-10-06：右栏不能越拉越长）。
import { ArrowsClockwise, CheckCircle, FileText, Signature } from '@phosphor-icons/react'
import { createElement } from 'react'

import type { AttentionItem } from '@/api/types'
import { Aurora, follow, Spot } from '@/components/Aurora'
import { Dot, ErrorNote, Skeleton } from '@/components/bits'
import { when } from '@/lib/format'
import type { Resource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

const SHOWN = 3

export function Attention({ items, onOpen }: {
  items: Resource<AttentionItem[]>
  onOpen: (project: string, workspace: string) => void
}) {
  const list = items.data
  return (
    <>
      <Card title="待你确认" items={list?.filter((i) => i.kind !== 'running')} error={items.error} empty="没有待你确认的"
            onOpen={onOpen} />
      <Card title="运行中" items={list?.filter((i) => i.kind === 'running')} error={items.error} empty="没有运行中的"
            onOpen={onOpen} />
    </>
  )
}

/** 一张卡：小标题 + 个数，下面最多三件，其余一行「还有 N 件」；空着一句淡字 */
function Card({ title, items, error, empty, onOpen }: {
  title: string; items: AttentionItem[] | undefined; error: string | null; empty: string
  onOpen: (project: string, workspace: string) => void
}) {
  return (
    <Aurora tone="quiet">
      <section aria-label={title} className="flex h-full flex-col px-2 pt-3 pb-2">
        <h2 className="flex items-baseline gap-2 px-3 pb-1">
          <span className="text-[0.875rem] font-semibold">{title}</span>
          {items && <span className="text-[0.8125rem] text-muted-foreground tabular">{items.length}</span>}
        </h2>
        {error && <div className="px-2 py-1"><ErrorNote text={error} /></div>}
        {!items && !error && <div className="px-3 py-2"><Skeleton lines={2} /></div>}
        {items && items.length === 0 && (
          <p className="flex flex-1 items-center gap-2 px-3 py-3 text-[0.8125rem] text-muted-foreground">
            <CheckCircle weight="fill" className="size-4 text-ok/70" aria-hidden />{empty}
          </p>
        )}
        {items && items.length > 0 && (
          <ul>
            {items.slice(0, SHOWN).map((i, n) => <Row key={`${i.project}/${i.workspace}/${i.kind}/${n}`} item={i} onOpen={onOpen} />)}
            {items.length > SHOWN && <li className="px-3 pt-1 pb-1 text-[0.75rem] text-muted-foreground">还有 {items.length - SHOWN} 件</li>}
          </ul>
        )}
      </section>
    </Aurora>
  )
}

/** 一件事说成什么：需求 / 有改动 / 某阶段的产出待确认 / 某能力 */
function what(item: AttentionItem): string {
  if (item.kind === 'requirement') return item.dirty ? '需求有改动' : '需求未确认'
  if (item.kind === 'sign') return item.stage ? `${item.stage}阶段待确认` : '断点待确认'
  return item.cap ?? '运行中'
}

function Row({ item, onOpen }: { item: AttentionItem; onOpen: (project: string, workspace: string) => void }) {
  const running = item.kind === 'running'
  const icon = item.kind === 'requirement' ? (item.dirty ? ArrowsClockwise : FileText) : Signature
  return (
    <li className="group/row relative">
      <button type="button" onClick={() => onOpen(item.project, item.workspace)} onMouseMove={follow}
              title={`${item.project_title} · ${item.workspace_title}`}
              className="relative isolate flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
        <Spot group="row" size="14rem" />
        <span aria-hidden="true"
              className={cn('flex size-8 shrink-0 items-center justify-center rounded-[10px] ring-1 ring-inset',
                            running ? 'bg-primary/10 text-primary ring-primary/15' : 'bg-wait-soft text-wait ring-wait/20')}>
          {running ? <Dot tone="primary" pulse /> : createElement(icon, { weight: 'fill', className: 'size-4' })}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.875rem] leading-snug font-medium">{item.workspace_title}</span>
          <span className={cn('block truncate text-[0.75rem]', running ? 'text-primary' : 'font-medium text-wait')}>
            {what(item)}{running && item.since && <span className="font-normal text-muted-foreground"> · {when(item.since)} 起</span>}
          </span>
        </span>
      </button>
    </li>
  )
}
