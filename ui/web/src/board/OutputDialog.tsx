// 一次产出的细节：最上面是产它的能力自己的进度面板（有的话，progress/），下面一块记录，最底下确认与删除。
// 看板里点开是**居中的悬浮窗**（主人 2026-10-05：侧滑没有边角、像粘在屏幕边上，改成上下左右居中、圆角、苹果那种玻璃）：
// 卡片色压到六成、背后的看板糊开提一点色，一圈亮边、顶上一道高光、投影长而软；只这块玻璃做 backdrop-filter，
// 遮罩只压暗不糊——两层模糊叠在一起是一团，全屏模糊还会跟着窗里的动效每帧重算。
// 记录是一张白底的表（与进度面板里的方块同一种材料）：每行左边一个说全了的名（「生成者」「所属流程」「读取的产出」，
// 主人：字要讲明白、不讲一半），右边是值，数字加重、单位与连接的字淡。末尾一行「生成文件」：一共几个、各是什么，
// 「打开目录」跳到文件镜头——不在窗里平铺（一次文献检索几百个文件，大半是原文切出来的图）；
// 文件镜头里同一份 `OutputBody` 嵌在右边，没有这一行（树就是清单）。能力返回给程序的那行结论（`literature ok …`）不上屏。
// 记录里的机器名字都翻过（P-21）：产出 id 写「设计 · 1」、产它的能力写名、参数写描述符的 label、流程写标题。
import { CheckCircle, FolderOpen, Trash, X } from '@phosphor-icons/react'
import { type ReactNode, useEffect, useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { Capability, OutputDetail, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/dialog'
import HoldButton from '@/components/reactbits/HoldButton'
import { SignKey } from '@/keys/SignKey'
import { span, when } from '@/lib/format'
import { byWord } from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
import { ProgressPanel } from '@/progress/ProgressPanel'

import { fileKinds, type NameOf, outputLine, outputName, tookWord } from './derive'


export function OutputDialog({ workspace, doc, catalog, oid, pending, onClose, onOpen, onChanged, onOpenFiles }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; catalog: Capability[]; oid: string | null
  /** 流程在这次产出后面的断点上等人确认 */
  pending: boolean
  onClose: () => void; onOpen: (oid: string) => void; onChanged: () => Promise<void>; onOpenFiles: (path: string) => void
}) {
  return (
    <Dialog open={oid !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent showCloseButton={false} aria-describedby={undefined}
                     className={'flex max-h-[calc(100dvh-3rem)] w-[min(46rem,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden rounded-[28px] p-0 duration-200 sm:max-w-none '
                                + 'bg-[color-mix(in_oklab,var(--card)_62%,transparent)] ring-1 ring-[var(--glass-rim)] backdrop-blur-[28px] backdrop-saturate-[1.8] '
                                + 'shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.06),0_28px_72px_-18px_rgb(0_0_0/0.38)]'}>
        <DialogClose asChild>
          <Button variant="ghost" size="icon-sm" className="absolute top-4 right-4 z-10 rounded-full" aria-label="关闭">
            <X />
          </Button>
        </DialogClose>
        <div className="min-h-0 overflow-y-auto">
          {oid && (
            <OutputBody workspace={workspace} doc={doc} catalog={catalog} oid={oid} pending={pending} onChanged={onChanged}
                        onRemoved={() => { onClose(); void onChanged() }}
                        title={(o) => <DialogTitle className="pr-10 font-serif text-[1.25rem] leading-snug font-semibold">{o.title}</DialogTitle>}
                        onOpen={onOpen} onOpenFiles={onOpenFiles} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 一次产出的记录与确认；给了 `onOpenFiles` 记录末尾再带「生成文件」一行。标题由外面给（悬浮窗里要 DialogTitle）。
 *  `doc` 与 `catalog` 只为翻译：阶段名、别的产出的标题、流程的标题、能力的名与参数的 label 都是后端给的，这里查表不猜。 */
export function OutputBody({ workspace, doc, catalog, oid, pending, onChanged, onRemoved, title, onOpen, onOpenFiles }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; catalog: Capability[]; oid: string; pending: boolean
  onChanged: () => Promise<void>
  /** 删了这次产出之后（悬浮窗要关）；不给就没有「删除」 */
  onRemoved?: () => void
  title: (o: { title: string }) => ReactNode; onOpen?: (oid: string) => void; onOpenFiles?: (path: string) => void
}) {
  const [epoch, setEpoch] = useState(0)
  const record = useResource(() => workspace.output(oid), [workspace.key, oid, epoch], `output:${workspace.key}:${oid}`)
  const reload = async () => { setEpoch((n) => n + 1); await onChanged() }
  // 运行中的产出跑完了：看板那一份（有作业在跑时工作区页每 10 秒重拉）里它的状态先变，这里跟着重拉一次记录。
  // 不自己轮询：看板那份已经在按时拉，状态变了跟一次就够（外层 #242）
  const listed = doc.stages.flatMap((s) => s.outputs).find((x) => x.id === oid)?.status
  const shown = record.data?.status
  const refetch = record.reload
  useEffect(() => {
    if (listed && shown && listed !== shown) void refetch()
  }, [listed, shown, refetch])
  if (record.error) return <div className="p-6"><ErrorNote text={record.error} /></div>
  if (!record.data) return <div className="p-6"><Skeleton lines={5} /></div>
  const o = record.data
  const nameOf: NameOf = (slug) => doc.stages.find((s) => s.slug === slug)?.name ?? slug
  const cap = catalog.find((c) => c.name === o.by)
  const titleOf = (name: string) => catalog.find((c) => c.name === name)?.title
  const labelOf = (param: string) => cap?.params.find((p) => p.name === param)?.label ?? param
  const flowTitle = o.flow ? doc.flows.find((f) => f.name === o.flow)?.title ?? o.flow : null
  const outputTitle = (id: string) => doc.stages.flatMap((s) => s.outputs).find((x) => x.id === id)?.title
  const kinds = fileKinds(o.files.map((f) => f.path))
  return (
    <>
      <header className="flex flex-col gap-1 px-6 pt-6 pb-3">
        {title(o)}
        <p className="t-label">{outputLine(o.id, nameOf)}</p>
      </header>
      <div className="space-y-5 px-6 pb-8">
        <ProgressPanel workspace={workspace} output={o} onOpenFile={onOpenFiles ? (path) => onOpenFiles(`${o.id}/${path}`) : undefined} />
        <dl className="divide-y divide-foreground/[0.06] rounded-2xl border border-foreground/10 bg-card px-4">
          <Row label="状态"><Status output={o} pending={pending} /></Row>
          <Row label="生成者">{byWord(o.by, titleOf)}</Row>
          {flowTitle && (
            <Row label="所属流程">{flowTitle}{o.step !== null && <Faint> · 第 {o.step + 1} 步</Faint>}</Row>
          )}
          {o.requirement !== null && <Row label="依据需求">v{o.requirement}</Row>}
          <Row label="读取的产出">
            {o.from.length === 0 ? <Faint>无</Faint> : (
              <ul className="flex flex-wrap gap-1.5">
                {o.from.map((id) => (
                  <li key={id}>
                    <button type="button" disabled={!onOpen} onClick={() => onOpen?.(id)} title={outputTitle(id)}
                            className="rounded-md bg-muted px-2 py-0.5 text-[0.8125rem] transition-colors enabled:hover:bg-accent enabled:hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
                      {outputName(id, nameOf)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Row>
          <Row label="运行时间">
            <span className="tabular-nums">{span(o.created_at, o.finished_at)}</span>
            {o.finished_at && <Faint> · 用时 {tookWord(o.created_at, o.finished_at)}</Faint>}
          </Row>
          {Object.keys(o.params).length > 0 && (
            <Row label="运行参数">
              <span className="flex flex-wrap gap-1.5">
                {Object.entries(o.params).map(([k, v]) => (
                  <span key={k} className="rounded-md bg-muted px-2 py-0.5 text-[0.8125rem]">
                    <span className="text-muted-foreground">{labelOf(k)}</span> <span className="font-medium tabular-nums">{String(v)}</span>
                  </span>
                ))}
              </span>
            </Row>
          )}
          {onOpenFiles && (
            <Row label="生成文件">
              <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="tabular-nums">
                  <span className="font-medium">{o.files.length}</span> 个
                  {kinds.length > 0 && <Faint>：{kinds.map(([kind, n]) => `${kind} ${n}`).join(' · ')}</Faint>}
                </span>
                <button type="button" onClick={() => onOpenFiles(o.id)}
                        className="ml-auto inline-flex items-center gap-1 self-center rounded text-[0.8125rem] text-primary transition-colors hover:text-primary/80 focus-visible:outline-2 focus-visible:outline-ring">
                  <FolderOpen className="size-3.5" aria-hidden />打开目录
                </button>
              </span>
            </Row>
          )}
        </dl>
        {o.error && <ErrorNote text={o.error} />}
        <div className="flex items-center gap-3">
          <SignKey workspace={workspace} output={o} reload={reload} />
          {onRemoved && <RemoveKey workspace={workspace} doc={doc} oid={oid} status={o.status} onRemoved={onRemoved} />}
        </div>
      </div>
    </>
  )
}

/** 记录的一行：左边说全了的名（淡），右边值 */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-baseline gap-x-3 py-2">
      <dt className="text-[0.8125rem] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[0.875rem]">{children}</dd>
    </div>
  )
}

/** 值里次要的那半句：单位、说明、分项 */
function Faint({ children }: { children: ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>
}

/** 状态一行：一个点一个词，与看板上那张小卡同一套词与颜色；确认过的带上确认时间 */
function Status({ output: o, pending }: { output: OutputDetail; pending: boolean }) {
  if (o.status === 'running') return <span className="inline-flex items-center gap-2 text-primary"><span className="size-2 animate-pulse rounded-full bg-primary" />运行中</span>
  if (o.status === 'failed') return <span className="inline-flex items-center gap-2 text-bad"><span className="size-2 rounded-full bg-bad" />失败</span>
  if (o.signed && !o.signed.stale) {
    return (
      <span className="inline-flex items-center gap-1.5 text-ok">
        <CheckCircle weight="fill" className="size-4" aria-hidden />已确认<Faint> · {when(o.signed.signed_at)}</Faint>
      </span>
    )
  }
  if (pending) return <span className="inline-flex items-center gap-2 font-medium text-wait"><span className="size-2 rounded-full bg-wait" />待确认</span>
  return (
    <span className="inline-flex items-center gap-2">
      <span className="size-2 rounded-full bg-muted-foreground/50" />完成{o.signed?.stale && <Faint> · 确认后又有改动</Faint>}
    </span>
  )
}

/** 删这次产出（主人 2026-09-22）：只有叶子（没被下游读过的）且没在跑才出现这枚键，按住一秒才删；服务那边还会再拒一遍。
 *  删不了时什么都不画（主人 2026-10-05：「被 literature/2 读过，先删下游」那句砍掉） */
function RemoveKey({ workspace, doc, oid, status, onRemoved }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; oid: string; status: string; onRemoved: () => void
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const read = doc.stages.flatMap((s) => s.outputs).some((x) => x.from.includes(oid))
  if (status === 'running' || read) return null
  const remove = () => {
    setFailed(null)
    workspace.removeOutput(oid).then(onRemoved).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <div className="ml-auto flex items-center gap-3">
      {failed && <span className="text-[0.75rem] text-bad">{failed}</span>}
      <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
    </div>
  )
}
