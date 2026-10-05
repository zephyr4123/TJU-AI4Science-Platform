// 一次产出的细节：最上面是产它的能力自己的进度面板（有的话，progress/），然后记录（来源、输入、在哪条流程第几步、按哪版需求）、
// 确认。看板里是侧滑，记录末尾一行「文件」：一共几个、各是什么，「打开目录」跳到文件镜头看正文——不在侧滑里平铺
// （主人 2026-10-05：一次文献检索几百个文件，大半是原文切出来的图）；文件镜头里同一份 `OutputBody` 嵌在右边，没有这一行（树就是清单）。
// 记录里的机器名字都翻过（P-21）：产出 id 写「设计 · 1」、产它的能力写名、参数写描述符的 label、流程写标题；文件名是文件本身，照写。
import { FolderOpen, Trash } from '@phosphor-icons/react'
import { type ReactNode, useEffect, useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { Capability, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import HoldButton from '@/components/reactbits/HoldButton'
import { SignKey } from '@/keys/SignKey'
import { when } from '@/lib/format'
import { byWord, outputWord } from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { ProgressPanel } from '@/progress/ProgressPanel'

import { filesWord, type NameOf, outputName } from './derive'


export function OutputSheet({ workspace, doc, catalog, oid, signHint, onClose, onOpen, onChanged, onOpenFiles }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; catalog: Capability[]; oid: string | null; signHint: string | null
  onClose: () => void; onOpen: (oid: string) => void; onChanged: () => Promise<void>; onOpenFiles: (path: string) => void
}) {
  return (
    <Sheet open={oid !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[40rem] data-[side=right]:sm:max-w-[40rem]">
        {oid && (
          <OutputBody workspace={workspace} doc={doc} catalog={catalog} oid={oid} signHint={signHint} onChanged={onChanged}
                      onRemoved={() => { onClose(); void onChanged() }}
                      title={(o) => <SheetTitle className="font-serif text-[1.25rem]">{o.title}</SheetTitle>}
                      onOpen={onOpen} onOpenFiles={onOpenFiles} />
        )}
      </SheetContent>
    </Sheet>
  )
}

/** 一次产出的记录、结论、确认；给了 `onOpenFiles` 记录末尾再带「文件」一行。标题由外面给（侧滑里要 SheetTitle）。
 *  `doc` 与 `catalog` 只为翻译：阶段名、别的产出的标题、流程的标题、能力的名与参数的 label 都是后端给的，这里查表不猜。 */
export function OutputBody({ workspace, doc, catalog, oid, signHint, onChanged, onRemoved, title, onOpen, onOpenFiles }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; catalog: Capability[]; oid: string; signHint: string | null
  onChanged: () => Promise<void>
  /** 删了这次产出之后（侧滑要关）；不给就没有「删除」 */
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
  return (
    <>
      <SheetHeader className="px-6 pt-6 pb-2">
        {title(o)}
        <p className="t-label">{outputName(o.id, nameOf)}</p>
      </SheetHeader>
      <div className="space-y-5 px-6 pb-8">
        <ProgressPanel workspace={workspace} output={o} onOpenFile={onOpenFiles ? (path) => onOpenFiles(`${o.id}/${path}`) : undefined} />
        <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1 text-[0.875rem]">
          <dt className="text-muted-foreground">来源</dt><dd>{byWord(o.by, titleOf)}</dd>
          <dt className="text-muted-foreground">状态</dt><dd className={cn(o.status === 'failed' && 'text-bad')}>{outputWord(o)}</dd>
          <dt className="text-muted-foreground">输入</dt>
          <dd>
            {o.from.length === 0 ? '—' : (
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
          </dd>
          {flowTitle && <><dt className="text-muted-foreground">流程</dt><dd>{flowTitle}{o.step !== null && ` · 第 ${o.step + 1} 项`}</dd></>}
          {o.requirement !== null && <><dt className="text-muted-foreground">需求</dt><dd>v{o.requirement}</dd></>}
          <dt className="text-muted-foreground">时间</dt><dd>{when(o.created_at)}{o.finished_at && ` → ${when(o.finished_at)}`}</dd>
          {Object.keys(o.params).length > 0 && (
            <><dt className="text-muted-foreground">参数</dt>
              <dd className="flex flex-wrap gap-x-4 gap-y-0.5">
                {Object.entries(o.params).map(([k, v]) => (
                  <span key={k}><span className="text-muted-foreground">{labelOf(k)}</span> <span className="tabular-nums">{String(v)}</span></span>
                ))}
              </dd></>
          )}
          {onOpenFiles && (
            <><dt className="text-muted-foreground">文件</dt>
              <dd className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="tabular-nums">{filesWord(o.files.map((f) => f.path))}</span>
                <button type="button" onClick={() => onOpenFiles(o.id)}
                        className="inline-flex items-center gap-1 self-center text-[0.8125rem] text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary focus-visible:outline-2 focus-visible:outline-ring">
                  <FolderOpen className="size-3.5" aria-hidden />打开目录
                </button>
              </dd></>
          )}
        </dl>
        {o.error && <ErrorNote text={o.error} />}
        {o.result && o.status === 'ok' && (
          <p className="rounded-lg bg-muted px-3 py-2 text-[0.875rem] leading-relaxed whitespace-pre-wrap">{o.result}</p>
        )}
        <SignKey workspace={workspace} output={o} hint={signHint} reload={reload} />
        {onRemoved && <RemoveKey workspace={workspace} doc={doc} oid={oid} status={o.status} onRemoved={onRemoved} />}
      </div>
    </>
  )
}

/** 删这次产出（主人 2026-09-22）：只有叶子（没被下游读过的）且没在跑才出现这枚键，按住一秒才删；服务那边还会再拒一遍 */
function RemoveKey({ workspace, doc, oid, status, onRemoved }: {
  workspace: WorkspaceClient; doc: WorkspaceDetail; oid: string; status: string; onRemoved: () => void
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const users = doc.stages.flatMap((s) => s.outputs).filter((x) => x.from.includes(oid)).map((x) => x.id)
  if (status === 'running') return null
  if (users.length > 0) {
    return <p className="text-[0.75rem] text-muted-foreground">被 {users.join('、')} 读过，先删下游才能删它</p>
  }
  const remove = () => {
    setFailed(null)
    workspace.removeOutput(oid).then(onRemoved).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <div className="flex items-center gap-3">
      <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
      {failed && <span className="text-[0.75rem] text-bad">{failed}</span>}
    </div>
  )
}
