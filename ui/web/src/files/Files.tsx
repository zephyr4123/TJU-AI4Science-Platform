// 文件镜头（外层 #111）：同一个工作区的另一个镜头——看板答「做到哪了、在等谁」，这里答「盘上到底有什么」。
// 左边一棵带平台语义的目录树：七个阶段目录显示阶段名与阶段图标（与看板同一套），每次产出那一层带状态（运行中 / 失败 /
// 已确认 / 冻结），`.ai4sci/` 灰显；一层一层懒加载。右边是选中的东西：文件按种类渲染（markdown、图片、csv / tsv 成表、
// 其它带行号原样），产出目录是它的记录与确认。只看不改：改动走对话，和需求同一条规矩（手改会撞冻结）。
import {
  CaretRight, CheckCircle, DownloadSimple, File, FileCode, FileText, Folder, FolderOpen, Image as ImageIcon,
  Lock, Table as TableIcon,
} from '@phosphor-icons/react'
import { createElement, useState } from 'react'

import { api } from '@/api/client'
import type { DirEntry, OutputBrief, WorkspaceDetail } from '@/api/types'
import { OutputBody } from '@/board/OutputSheet'
import { Dot, ErrorNote, Skeleton } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { bytes } from '@/lib/format'
import { outputWord } from '@/lib/humanize'
import { stageIcon } from '@/lib/stages'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { ancestors, fileKind, meaningOf, orderRoot, outputIdOf, parseTable, referencedIds, type RowMeaning } from './derive'

/** 进来先看需求：树的根上最要紧的那份文件 */
const DEFAULT_FILE = 'requirement.md'

/** `focus` 是从看板「打开目录」带过来的产出路径：进来就展开到它、选中它（父组件按 focus 给 key，换了就重建） */
export function Files({ workspace, epoch, focus }: { workspace: string; epoch: number; focus: string | null }) {
  const doc = useResource(() => api.workspace(workspace), [workspace, epoch])
  const [selected, setSelected] = useState<string>(focus ?? DEFAULT_FILE)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(ancestors(focus ?? DEFAULT_FILE).concat(focus ? [focus] : [])))
  const toggle = (path: string) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(path)) next.delete(path); else next.add(path)
    return next
  })

  if (doc.error) return <div className="p-6"><ErrorNote text={doc.error} /></div>
  if (!doc.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const referenced = referencedIds(data)
  const meaning = (path: string) => meaningOf(path, data, referenced)
  const picked = meaning(selected)
  return (
    <div className="grid h-full grid-cols-[17rem_minmax(0,1fr)]">
      <nav aria-label="文件" className="overflow-y-auto border-r bg-card/70 py-2 backdrop-blur-sm">
        <DirRows workspace={workspace} path="" depth={0} epoch={epoch} expanded={expanded} selected={selected}
                 meaning={meaning} order={(entries) => orderRoot(entries, data)} onToggle={toggle} onSelect={setSelected} />
      </nav>
      <section className="min-w-0 overflow-auto bg-background/85 backdrop-blur-sm" aria-label="内容">
        {picked.kind === 'output'
          ? <OutputBody workspace={workspace} oid={picked.output.id} signHint={null} onChanged={doc.reload} showFiles={false}
                        title={(o) => <h2 className="font-serif text-[1.25rem] font-semibold">{o.title}</h2>} />
          : <FilePane key={selected} workspace={workspace} path={selected} epoch={epoch} doc={data} />}
      </section>
    </div>
  )
}

/** 一个目录的一层：懒加载；每行按它在工作区里的意思画。`order` 只有根一层给（按工作区骨架排） */
function DirRows({ workspace, path, depth, epoch, expanded, selected, meaning, order, onToggle, onSelect }: {
  workspace: string; path: string; depth: number; epoch: number; expanded: Set<string>; selected: string
  meaning: (path: string) => RowMeaning; order?: (entries: DirEntry[]) => DirEntry[]
  onToggle: (path: string) => void; onSelect: (path: string) => void
}) {
  const listing = useResource(() => api.files(workspace, path), [workspace, path, epoch])
  if (listing.error) return <p className="px-3 py-1 text-[0.75rem] text-bad" style={{ paddingLeft: indent(depth) }}>{listing.error}</p>
  if (!listing.data) return <div className="px-3 py-1" style={{ paddingLeft: indent(depth) }}><Skeleton lines={2} /></div>
  const entries = order ? order(listing.data.entries) : listing.data.entries
  return (
    <ul>
      {entries.map((entry) => {
        const full = path ? `${path}/${entry.name}` : entry.name
        const open = expanded.has(full)
        const what = meaning(full)
        return (
          <li key={entry.name}>
            <Row entry={entry} path={full} depth={depth} open={open} selected={selected === full} meaning={what}
                 onToggle={() => onToggle(full)}
                 onClick={() => {
                   // 文件：选中看内容。产出那一层：选中看记录，同时展开（不收）。别的目录：开合
                   if (entry.kind === 'file') return onSelect(full)
                   if (what.kind === 'output') { onSelect(full); if (!open) onToggle(full); return }
                   onToggle(full)
                 }} />
            {entry.kind === 'dir' && open && (
              <DirRows workspace={workspace} path={full} depth={depth + 1} epoch={epoch} expanded={expanded} selected={selected}
                       meaning={meaning} onToggle={onToggle} onSelect={onSelect} />
            )}
          </li>
        )
      })}
    </ul>
  )
}

const indent = (depth: number) => `${0.5 + depth * 0.875}rem`

function Row({ entry, path, depth, open, selected, meaning, onClick, onToggle }: {
  entry: DirEntry; path: string; depth: number; open: boolean; selected: boolean; meaning: RowMeaning
  onClick: () => void; onToggle: () => void
}) {
  const dir = entry.kind === 'dir'
  const dim = meaning.kind === 'platform' || (meaning.kind === 'plain' && entry.name.startsWith('.'))
  return (
    <div className={cn('flex items-center gap-1.5 py-[3px] pr-2 text-[0.8125rem] leading-tight hover:bg-accent/60',
                       selected && 'bg-primary/10 text-primary', dim && 'text-muted-foreground/70')}
         style={{ paddingLeft: indent(depth) }}>
      {/* 折角单独可点：产出那一层点正文是看记录，收起来只靠折角 */}
      <button type="button" onClick={onToggle} disabled={!dir} aria-label={dir ? (open ? '收起' : '展开') : undefined} tabIndex={dir ? 0 : -1}
              className={cn('flex size-4 shrink-0 items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-ring', !dir && 'invisible')}>
        <CaretRight weight="bold" aria-hidden className={cn('size-3 text-muted-foreground/60 transition-transform', open && 'rotate-90')} />
      </button>
      <button type="button" onClick={onClick} aria-current={selected ? 'true' : undefined} title={path}
              className="flex min-w-0 flex-1 items-center gap-1.5 text-left focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring">
        <RowIcon entry={entry} meaning={meaning} open={open} />
        <RowLabel entry={entry} meaning={meaning} />
      </button>
    </div>
  )
}

function RowIcon({ entry, meaning, open }: { entry: DirEntry; meaning: RowMeaning; open: boolean }) {
  const cls = 'size-4 shrink-0'
  if (meaning.kind === 'stage') return createElement(stageIcon(meaning.stage.name), { weight: 'duotone', 'aria-hidden': true, className: cn(cls, 'text-foreground/70') })
  if (meaning.kind === 'output') return null
  if (entry.kind === 'dir') return open ? <FolderOpen className={cn(cls, 'text-muted-foreground')} aria-hidden /> : <Folder className={cn(cls, 'text-muted-foreground')} aria-hidden />
  const kind = fileKind(entry.name)
  const Icon = kind === 'markdown' ? FileText : kind === 'image' ? ImageIcon : kind === 'table' ? TableIcon
    : /\.(py|sh|ya?ml|json|toml|cfg|ini|lock)$/i.test(entry.name) ? FileCode : File
  return <Icon className={cn(cls, 'text-muted-foreground/80')} aria-hidden />
}

/** 阶段目录写阶段名；产出那一层是 mono 编号 + 状态词（冻结另加一把锁）；其它就是文件名 */
function RowLabel({ entry, meaning }: { entry: DirEntry; meaning: RowMeaning }) {
  if (meaning.kind === 'stage') return <span className="font-serif font-semibold">{meaning.stage.name}</span>
  if (meaning.kind === 'output') return <OutputLabel n={entry.name} output={meaning.output} frozen={meaning.frozen} />
  return <span className="min-w-0 flex-1 truncate font-mono">{entry.name}</span>
}

function OutputLabel({ n, output, frozen }: { n: string; output: OutputBrief; frozen: boolean }) {
  const word = outputWord(output)
  const tone = output.status === 'running' ? 'text-primary' : output.status === 'failed' ? 'text-bad'
    : output.signed && !output.signed.stale ? 'text-ok' : 'text-muted-foreground'
  return (
    <span className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className="font-mono tabular-nums">{n}</span>
      <span className={cn('flex items-center gap-1 text-[0.6875rem]', tone)}>
        {output.status === 'running' && <Dot tone="primary" pulse />}
        {output.signed && !output.signed.stale && <CheckCircle weight="fill" className="size-3" aria-hidden />}
        {word}
      </span>
      {frozen && <Lock weight="fill" className="ml-auto size-3 shrink-0 text-muted-foreground/70" aria-label="冻结" />}
    </span>
  )
}

/** 右边：一个文件。顶上一行说它是哪个文件、多大、属于哪次产出；正文按种类渲染 */
function FilePane({ workspace, path, epoch, doc }: { workspace: string; path: string; epoch: number; doc: WorkspaceDetail }) {
  const file = useResource(() => api.file(workspace, path), [workspace, path, epoch])
  const oid = outputIdOf(path, doc)
  const output = oid ? doc.stages.flatMap((s) => s.outputs).find((o) => o.id === oid) ?? null : null
  if (file.error) return <div className="p-6"><ErrorNote text={file.error} /></div>
  if (!file.data) return <div className="p-6"><Skeleton lines={8} /></div>
  const f = file.data
  const kind = fileKind(path)
  return (
    <article className="min-h-full">
      <header className="sticky top-0 z-10 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b bg-background/90 px-5 py-2.5 backdrop-blur-sm">
        <span className="min-w-0 truncate font-mono text-[0.8125rem]">{path}</span>
        <span className="t-label tabular-nums">{bytes(f.size)}</span>
        {output && <span className="t-label">{output.title} · {outputWord(output)}</span>}
        {f.text === null && (
          <a href={api.rawUrl(workspace, path)} download className="ml-auto inline-flex items-center gap-1 text-[0.8125rem] text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary">
            <DownloadSimple className="size-3.5" aria-hidden />下载
          </a>
        )}
      </header>
      <div className="px-5 py-4">
        {kind === 'image'
          ? <img src={api.rawUrl(workspace, path)} alt={path.split('/').pop() ?? path} className="max-w-full rounded-lg border" />
          : f.text === null
            ? <p className="t-label">二进制文件</p>
            : kind === 'markdown'
              ? <Markdown text={f.text} className="max-w-[72ch]" />
              : kind === 'table'
                ? <DataTable text={f.text} path={path} />
                : <Code text={f.text} />}
        {f.truncated && <p className="t-label mt-4">文件太大，只显示开头 {bytes(f.text?.length ?? 0)}。</p>}
      </div>
    </article>
  )
}

/** 原样带行号；不折行，横向滚 */
function Code({ text }: { text: string }) {
  const lines = text.replace(/\n$/, '').split('\n')
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] overflow-x-auto font-mono text-[0.75rem] leading-[1.65]">
      {lines.map((line, i) => (
        <div key={i} className="contents">
          <span className="pr-4 text-right text-muted-foreground/50 tabular-nums select-none">{i + 1}</span>
          <span className="whitespace-pre">{line || ' '}</span>
        </div>
      ))}
    </div>
  )
}

function DataTable({ text, path }: { text: string; path: string }) {
  const { header, rows, more } = parseTable(text, path)
  return (
    <>
      <Table className="font-mono text-[0.75rem]">
        <TableHeader>
          <TableRow>{header.map((h, i) => <TableHead key={i} className="whitespace-nowrap">{h}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, r) => (
            <TableRow key={r}>{row.map((cell, c) => <TableCell key={c} className="whitespace-nowrap tabular-nums">{cell}</TableCell>)}</TableRow>
          ))}
        </TableBody>
      </Table>
      {more > 0 && <p className="t-label mt-3">还有 {more} 行。</p>}
    </>
  )
}
