// 一次产出的细节：记录（来源、输入、在哪条流第几步、按哪版需求）、确认、目录里的文件——按文件种类通用渲染
// （markdown 排版、json / yaml / tsv 原样、大的与二进制只给名字），能力没配专门视图也看得见东西（P-13 在页面上的对应物）。
// 看板里是侧滑（带文件清单与「打开目录」跳到文件镜头）；文件镜头里同一份 `OutputBody` 嵌在右边，不带文件清单（树就是清单）。
import { FolderOpen } from '@phosphor-icons/react'
import { type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { OutputFile } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { SignKey } from '@/keys/SignKey'
import { bytes, when } from '@/lib/format'
import { byWord, outputWord } from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

export function OutputSheet({ workspace, oid, signHint, onClose, onChanged, onOpenFiles }: {
  workspace: string; oid: string | null; signHint: string | null; onClose: () => void; onChanged: () => Promise<void>
  onOpenFiles: (path: string) => void
}) {
  return (
    <Sheet open={oid !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[40rem] data-[side=right]:sm:max-w-[40rem]">
        {oid && (
          <OutputBody workspace={workspace} oid={oid} signHint={signHint} onChanged={onChanged} showFiles
                      title={(o) => <SheetTitle className="font-serif text-[1.25rem]">{o.title}</SheetTitle>}
                      onOpenFiles={onOpenFiles} />
        )}
      </SheetContent>
    </Sheet>
  )
}

/** 一次产出的记录、结论、确认；`showFiles` 再带目录里的文件清单。标题由外面给（侧滑里要 SheetTitle）。 */
export function OutputBody({ workspace, oid, signHint, onChanged, showFiles, title, onOpenFiles }: {
  workspace: string; oid: string; signHint: string | null; onChanged: () => Promise<void>; showFiles: boolean
  title: (o: { title: string }) => ReactNode; onOpenFiles?: (path: string) => void
}) {
  const [epoch, setEpoch] = useState(0)
  const doc = useResource(() => api.output(workspace, oid), [workspace, oid, epoch])
  const reload = async () => { setEpoch((n) => n + 1); await onChanged() }
  if (doc.error) return <div className="p-6"><ErrorNote text={doc.error} /></div>
  if (!doc.data) return <div className="p-6"><Skeleton lines={5} /></div>
  const o = doc.data
  return (
    <>
      <SheetHeader className="px-6 pt-6 pb-2">
        {title(o)}
        <p className="flex items-center gap-3">
          <span className="t-label font-mono">{o.id}</span>
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
          <dt className="text-muted-foreground">来源</dt><dd>{byWord(o.by)}</dd>
          <dt className="text-muted-foreground">状态</dt><dd className={cn(o.status === 'failed' && 'text-bad')}>{outputWord(o)}</dd>
          <dt className="text-muted-foreground">输入</dt><dd className="font-mono text-[0.8125rem]">{o.from.length ? o.from.join(', ') : '—'}</dd>
          {o.flow && <><dt className="text-muted-foreground">流</dt><dd>{o.flow}{o.step !== null && ` · 第 ${o.step + 1} 步`}</dd></>}
          {o.requirement !== null && <><dt className="text-muted-foreground">需求</dt><dd>v{o.requirement}</dd></>}
          <dt className="text-muted-foreground">时间</dt><dd>{when(o.created_at)}{o.finished_at && ` → ${when(o.finished_at)}`}</dd>
          {Object.keys(o.params).length > 0 && (
            <><dt className="text-muted-foreground">参数</dt>
              <dd className="font-mono text-[0.8125rem]">{Object.entries(o.params).map(([k, v]) => `${k}=${String(v)}`).join('  ')}</dd></>
          )}
        </dl>
        {o.error && <ErrorNote text={o.error} />}
        {o.result && o.status === 'ok' && (
          <p className="rounded-lg bg-muted px-3 py-2 font-mono text-[0.75rem] leading-relaxed whitespace-pre-wrap break-all text-muted-foreground">{o.result}</p>
        )}
        <SignKey workspace={workspace} output={o} hint={signHint} reload={reload} />
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
