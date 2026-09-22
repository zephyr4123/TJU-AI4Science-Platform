// 一次产出的细节：记录（来源、输入、在哪条流程第几步、按哪版需求）、确认、目录里的文件——按文件种类通用渲染
// （markdown 排版、json / yaml / tsv 原样、大的与二进制只给名字），能力没配专门视图也看得见东西（P-13 在页面上的对应物）。
// 看板里是侧滑（带文件清单与「打开目录」跳到文件镜头）；文件镜头里同一份 `OutputBody` 嵌在右边，不带文件清单（树就是清单）。
// 记录里的机器名字都翻过（P-21）：产出 id 写「设计 · 1」、产它的能力写名、参数写描述符的 label、流程写标题；文件名是文件本身，照写。
import { FolderOpen, Trash } from '@phosphor-icons/react'
import { type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { Capability, OutputFile, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import HoldButton from '@/components/reactbits/HoldButton'
import { SignKey } from '@/keys/SignKey'
import { bytes, when } from '@/lib/format'
import { byWord, outputWord } from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { type NameOf, outputName } from './derive'

export function OutputSheet({ workspace, doc, catalog, oid, signHint, onClose, onOpen, onChanged, onOpenFiles }: {
  workspace: string; doc: WorkspaceDetail; catalog: Capability[]; oid: string | null; signHint: string | null
  onClose: () => void; onOpen: (oid: string) => void; onChanged: () => Promise<void>; onOpenFiles: (path: string) => void
}) {
  return (
    <Sheet open={oid !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[40rem] data-[side=right]:sm:max-w-[40rem]">
        {oid && (
          <OutputBody workspace={workspace} doc={doc} catalog={catalog} oid={oid} signHint={signHint} onChanged={onChanged} showFiles
                      onRemoved={() => { onClose(); void onChanged() }}
                      title={(o) => <SheetTitle className="font-serif text-[1.25rem]">{o.title}</SheetTitle>}
                      onOpen={onOpen} onOpenFiles={onOpenFiles} />
        )}
      </SheetContent>
    </Sheet>
  )
}

/** 一次产出的记录、结论、确认；`showFiles` 再带目录里的文件清单。标题由外面给（侧滑里要 SheetTitle）。
 *  `doc` 与 `catalog` 只为翻译：阶段名、别的产出的标题、流程的标题、能力的名与参数的 label 都是后端给的，这里查表不猜。 */
export function OutputBody({ workspace, doc, catalog, oid, signHint, onChanged, onRemoved, showFiles, title, onOpen, onOpenFiles }: {
  workspace: string; doc: WorkspaceDetail; catalog: Capability[]; oid: string; signHint: string | null
  onChanged: () => Promise<void>; showFiles: boolean
  /** 删了这次产出之后（侧滑要关）；不给就没有「删除」 */
  onRemoved?: () => void
  title: (o: { title: string }) => ReactNode; onOpen?: (oid: string) => void; onOpenFiles?: (path: string) => void
}) {
  const [epoch, setEpoch] = useState(0)
  const record = useResource(() => api.output(workspace, oid), [workspace, oid, epoch])
  const reload = async () => { setEpoch((n) => n + 1); await onChanged() }
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
        <p className="flex items-center gap-3">
          <span className="t-label">{outputName(o.id, nameOf)}</span>
          {onOpenFiles && (
            <button type="button" onClick={() => onOpenFiles(o.id)}
                    className="inline-flex items-center gap-1 text-[0.8125rem] text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary focus-visible:outline-2 focus-visible:outline-ring">
              <FolderOpen className="size-3.5" aria-hidden />打开目录
            </button>
          )}
        </p>
      </SheetHeader>
      <div className="space-y-5 px-6 pb-8">
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
        </dl>
        {o.error && <ErrorNote text={o.error} />}
        {o.result && o.status === 'ok' && (
          <p className="rounded-lg bg-muted px-3 py-2 text-[0.875rem] leading-relaxed whitespace-pre-wrap">{o.result}</p>
        )}
        <SignKey workspace={workspace} output={o} hint={signHint} reload={reload} />
        {onRemoved && <RemoveKey workspace={workspace} doc={doc} oid={oid} status={o.status} onRemoved={onRemoved} />}
        {showFiles && (
          <section>
            <h3 className="t-step">文件</h3>
            {o.files.length === 0 && <p className="t-label mt-1">暂无文件</p>}
            <ul className="mt-2 space-y-2">
              {o.files.map((f) => <FileRow key={f.path} file={f} />)}
            </ul>
          </section>
        )}
      </div>
    </>
  )
}

/** 一个文件：小文本展开看（markdown 排版、别的原样），大的与二进制只有名字与大小。 */
function FileRow({ file }: { file: OutputFile }) {
  const [open, setOpen] = useState(file.path.endsWith('.md'))
  const readable = file.text !== undefined
  return (
    <li className="rounded-xl border bg-card">
      <button type="button" disabled={!readable} onClick={() => setOpen(!open)} aria-expanded={open}
              className="flex w-full items-center gap-2 px-3 py-2 text-left font-mono text-[0.8125rem] disabled:cursor-default">
        <span className="min-w-0 flex-1 truncate">{file.path}</span>
        <span className="t-label tabular-nums">{bytes(file.size)}</span>
      </button>
      {open && readable && (
        <div className="border-t px-3 py-3">
          {file.path.endsWith('.md')
            ? <Markdown text={file.text!} />
            : <pre className="max-h-[24rem] overflow-auto text-[0.75rem] leading-relaxed whitespace-pre-wrap break-all">{file.text}</pre>}
        </div>
      )}
    </li>
  )
}


/** 删这次产出（主人 2026-09-22）：只有叶子（没被下游读过的）且没在跑才出现这枚键，按住一秒才删；服务那边还会再拒一遍 */
function RemoveKey({ workspace, doc, oid, status, onRemoved }: {
  workspace: string; doc: WorkspaceDetail; oid: string; status: string; onRemoved: () => void
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const users = doc.stages.flatMap((s) => s.outputs).filter((x) => x.from.includes(oid)).map((x) => x.id)
  if (status === 'running') return null
  if (users.length > 0) {
    return <p className="text-[0.75rem] text-muted-foreground">被 {users.join('、')} 读过，先删下游才能删它</p>
  }
  const remove = () => {
    setFailed(null)
    api.removeOutput(workspace, oid).then(onRemoved).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <div className="flex items-center gap-3">
      <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
      {failed && <span className="text-[0.75rem] text-bad">{failed}</span>}
    </div>
  )
}
