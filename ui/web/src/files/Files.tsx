// 文件镜头（外层 #111）：同一个工作区的另一个镜头——看板答「做到哪了、在等谁」，这里答「盘上到底有什么」。
// 左边一棵大纲式的树，直接印在底上不加框：每一级一根浅灰缩进导线（不上色，主人：蓝线太丑）；七个阶段目录写阶段名 + 阶段图标
// （与看板同一套），行距统一不分组（主人：分组的空行看着像没对齐）；每次产出那一层是编号 + 右对齐的状态词（冻结另加一把锁）；
// `.ai4sci/` 灰显；一层一层懒加载。
// 右边是整个镜头里唯一抬起的面：头部是「位置」（面包屑写平台语义 + 文件名大字 + 大小与行数；没有「下载」，文件本来就在盘上），正文按种类渲染——代码高亮带行号、
// markdown 排版、csv / tsv 成表、图片居中；产出那一层是它的记录与确认。只看不改：改动走对话，和需求同一条规矩（手改会撞冻结）。
import {
  CaretRight, CheckCircle, File, FileCode, FileText, Folder, FolderOpen, Image as ImageIcon, Kanban, Lock,
  Table as TableIcon,
} from '@phosphor-icons/react'
import { createElement, type ReactNode, useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { Capability, DirEntry, OutputBrief, WorkspaceDetail } from '@/api/types'
import { OutputBody } from '@/board/OutputSheet'
import { Dot, ErrorNote, Skeleton } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { bytes } from '@/lib/format'
import { outputWord } from '@/lib/humanize'
import { stageIcon } from '@/lib/stages'
import { type Resource, useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { ancestors, fileKind, meaningOf, orderRoot, outputIdOf, parseTable, referencedIds, type RowMeaning } from './derive'
import { highlight, languageOf } from './highlight'

/** 进来先看需求：树的根上最要紧的那份文件 */
const DEFAULT_FILE = 'requirement.md'

/** `focus` 是从看板「打开目录」带过来的产出路径：进来就展开到它、选中它（父组件按 focus 给 key，换了就重建）。
 *  工作区那一整份 `doc` 由父组件拉、与看板共用；`epoch` 是对话的轮次，换了就重读目录与文件 */
export function Files({ workspace, doc, caps, epoch, focus, onOpenBoard }: {
  workspace: WorkspaceClient; doc: Resource<WorkspaceDetail>; caps: Resource<Capability[]>; epoch: number; focus: string | null
  onOpenBoard: (oid: string) => void
}) {
  const [selected, setSelected] = useState<string>(focus ?? DEFAULT_FILE)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(ancestors(focus ?? DEFAULT_FILE).concat(focus ? [focus] : [])))
  const toggle = (path: string) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(path)) next.delete(path); else next.add(path)
    return next
  })
  // 面包屑点回上一级：展开到那儿；是产出就选中它看记录
  const reveal = (path: string, output: boolean) => {
    setExpanded((prev) => new Set([...prev, ...ancestors(path), path]))
    if (output) setSelected(path)
  }

  if (doc.error) return <div className="p-6"><ErrorNote text={doc.error} /></div>
  if (!doc.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const referenced = referencedIds(data)
  const meaning = (path: string) => meaningOf(path, data, referenced)
  const picked = meaning(selected)
  return (
    <div className="grid h-full grid-cols-[17rem_minmax(0,1fr)]">
      <nav aria-label="文件" className="overflow-y-auto py-3 pr-2">
        <DirRows workspace={workspace} path="" depth={0} epoch={epoch} expanded={expanded} selected={selected}
                 meaning={meaning} order={(entries) => orderRoot(entries, data)} onToggle={toggle} onSelect={setSelected} />
      </nav>
      <section aria-label="内容"
               className="my-3 mr-3 min-w-0 overflow-auto rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
        {picked.kind === 'output'
          ? (
            <>
              <Location path={selected} meaning={meaning} onReveal={reveal} />
              <OutputBody workspace={workspace} doc={data} catalog={caps.data ?? []} oid={picked.output.id} signHint={null}
                          onChanged={doc.reload} showFiles={false} onOpen={(oid) => reveal(oid, true)}
                          title={(o) => <h2 className="font-serif text-[1.25rem] font-semibold">{o.title}</h2>} />
            </>
          )
          : <FilePane key={selected} workspace={workspace} path={selected} epoch={epoch} doc={data} meaning={meaning}
                      onReveal={reveal} onOpenBoard={onOpenBoard} />}
      </section>
    </div>
  )
}

// ── 树 ───────────────────────────────────────────────────────────────────
const indent = (depth: number) => 0.75 + depth * 0.875
/** 这一级的缩进导线画在上一级折角的正中 */
const guideLeft = (depth: number) => `${indent(depth - 1) + 0.5}rem`

/** 一个目录的一层：懒加载；每行按它在工作区里的意思画。`order` 只有根一层给（按工作区骨架排） */
function DirRows({ workspace, path, depth, epoch, expanded, selected, meaning, order, onToggle, onSelect }: {
  workspace: WorkspaceClient; path: string; depth: number; epoch: number; expanded: Set<string>; selected: string
  meaning: (path: string) => RowMeaning; order?: (entries: DirEntry[]) => DirEntry[]
  onToggle: (path: string) => void; onSelect: (path: string) => void
}) {
  const listing = useResource(() => workspace.files(path), [workspace.key, path, epoch], `files:${workspace.key}:${path}`)
  if (listing.error) return <p className="py-1 pr-2 text-[0.75rem] text-bad" style={{ paddingLeft: `${indent(depth)}rem` }}>{listing.error}</p>
  // 子目录加载不画占位：本地请求几十毫秒就回，骨架闪一下又没了（空目录尤其明显）；折角一转就是反馈。骨架只给根那一层
  if (!listing.data) return depth === 0 ? <div className="px-3 py-1"><Skeleton lines={4} /></div> : null
  const entries = order ? order(listing.data.entries) : listing.data.entries
  if (entries.length === 0) {
    return <p className="py-[3px] pr-2 text-[0.75rem] text-muted-foreground/60" style={{ paddingLeft: `${indent(depth) + 1.375}rem` }}>空</p>
  }
  return (
    <ul className="relative">
      {depth > 0 && <span aria-hidden className="absolute top-0 bottom-0 w-px bg-border" style={{ left: guideLeft(depth) }} />}
      {entries.map((entry) => {
        const full = path ? `${path}/${entry.name}` : entry.name
        const open = expanded.has(full)
        const what = meaning(full)
        return (
          <li key={entry.name}>
            <Row entry={entry} path={full} depth={depth} open={open} selected={selected === full} meaning={what}
                 onToggle={() => onToggle(full)}
                 onClick={() => {
                   // 文件：选中看内容。产出那一层：第一下选中看记录并展开，已选中再点就开合（主人：点第二下收不回去）。别的目录：开合
                   if (entry.kind === 'file') return onSelect(full)
                   if (what.kind === 'output' && selected !== full) { onSelect(full); if (!open) onToggle(full); return }
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

function Row({ entry, path, depth, open, selected, meaning, onClick, onToggle }: {
  entry: DirEntry; path: string; depth: number; open: boolean; selected: boolean; meaning: RowMeaning
  onClick: () => void; onToggle: () => void
}) {
  const dir = entry.kind === 'dir'
  const dim = meaning.kind === 'platform' || (meaning.kind === 'plain' && entry.name.startsWith('.'))
  return (
    <div className={cn('relative flex items-center gap-1.5 py-[3px] pr-2 text-[0.8125rem] leading-tight hover:bg-foreground/[0.035]',
                       selected && 'font-medium text-foreground shadow-[inset_2px_0_0_var(--color-primary)]', dim && 'text-muted-foreground/70')}
         style={{ paddingLeft: `${indent(depth)}rem` }}>
      {/* 折角单独可点：产出那一层第一下点正文是看记录，不想换选中也能收 */}
      <button type="button" onClick={onToggle} disabled={!dir} aria-label={dir ? (open ? '收起' : '展开') : undefined} tabIndex={dir ? 0 : -1}
              className={cn('relative z-10 flex size-4 shrink-0 items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-ring', !dir && 'invisible')}>
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
    : languageOf(entry.name) ? FileCode : File
  return <Icon className={cn(cls, 'text-muted-foreground/80')} aria-hidden />
}

/** 阶段目录写阶段名；产出那一层是 mono 编号 + 右对齐的状态词（冻结另加一把锁）；其它就是文件名 */
function RowLabel({ entry, meaning }: { entry: DirEntry; meaning: RowMeaning }) {
  if (meaning.kind === 'stage') return <span className="font-serif text-[0.875rem] font-semibold">{meaning.stage.name}</span>
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
      <span className={cn('ml-auto flex items-center gap-1 text-[0.6875rem] font-normal', tone)}>
        {output.status === 'running' && <Dot tone="primary" pulse />}
        {output.signed && !output.signed.stale && <CheckCircle weight="fill" className="size-3" aria-hidden />}
        {word}
      </span>
      {frozen && <Lock weight="fill" className="size-3 shrink-0 text-muted-foreground/70" aria-label="冻结" />}
    </span>
  )
}

// ── 内容 ─────────────────────────────────────────────────────────────────
/** 面包屑写平台语义：设计 › 1 · 已确认 › harness；每一段可点回上一级 */
function Location({ path, meaning, onReveal }: { path: string; meaning: (path: string) => RowMeaning; onReveal: (path: string, output: boolean) => void }) {
  const crumbs = ancestors(path)
  if (crumbs.length === 0) return null
  return (
    <nav aria-label="位置" className="flex flex-wrap items-center gap-x-1 gap-y-0.5 px-6 pt-4 text-[0.75rem] text-muted-foreground">
      {crumbs.map((crumb, i) => {
        const what = meaning(crumb)
        const label: ReactNode = what.kind === 'stage'
          ? <>{createElement(stageIcon(what.stage.name), { weight: 'duotone', 'aria-hidden': true, className: 'size-3.5' })}{what.stage.name}</>
          : what.kind === 'output' ? `${crumb.split('/')[1]} · ${outputWord(what.output)}`
            : crumb.split('/').pop()
        return (
          <span key={crumb} className="flex items-center gap-1">
            <button type="button" onClick={() => onReveal(crumb, what.kind === 'output')}
                    className="inline-flex items-center gap-1 rounded hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
              {label}
            </button>
            {i < crumbs.length - 1 && <CaretRight className="size-3 text-muted-foreground/50" aria-hidden />}
          </span>
        )
      })}
    </nav>
  )
}

/** 一个文件：位置、名字大字、大小与行数；正文按种类渲染 */
function FilePane({ workspace, path, epoch, doc, meaning, onReveal, onOpenBoard }: {
  workspace: WorkspaceClient; path: string; epoch: number; doc: WorkspaceDetail; meaning: (path: string) => RowMeaning
  onReveal: (path: string, output: boolean) => void; onOpenBoard: (oid: string) => void
}) {
  const file = useResource(() => workspace.file(path), [workspace.key, path, epoch], `file:${workspace.key}:${path}`)
  const oid = outputIdOf(path, doc)
  if (file.error) return <div className="p-6"><ErrorNote text={file.error} /></div>
  if (!file.data) return <div className="p-6"><Skeleton lines={8} /></div>
  const f = file.data
  const kind = fileKind(path)
  const name = path.split('/').pop() ?? path
  const lines = f.text === null ? null : f.text.replace(/\n$/, '').split('\n').length
  return (
    <article className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-foreground/[0.06] bg-card/95 pb-3 backdrop-blur-sm">
        <Location path={path} meaning={meaning} onReveal={onReveal} />
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-6 pt-1">
          <h2 className="min-w-0 truncate font-mono text-[1.0625rem] font-medium">{name}</h2>
          <span className="t-label tabular-nums">{bytes(f.size)}{lines !== null && ` · ${lines} 行`}</span>
          {oid && (
            <button type="button" onClick={() => onOpenBoard(oid)}
                    className="ml-auto inline-flex items-center gap-1 text-[0.8125rem] text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary focus-visible:outline-2 focus-visible:outline-ring">
              <Kanban className="size-3.5" aria-hidden />在看板打开
            </button>
          )}
        </div>
      </header>
      {kind === 'image'
        ? <div className="m-6 flex justify-center rounded-xl bg-muted/40 p-6"><img src={workspace.rawUrl(path)} alt={name} className="max-w-full rounded-md" /></div>
        : f.text === null
          ? <p className="t-label px-6 py-5">二进制文件，页面不显示。</p>
          : kind === 'markdown'
            ? <div className="px-6 py-5"><Markdown text={f.text} className="max-w-[72ch]" /></div>
            : kind === 'table'
              ? <DataTable text={f.text} path={path} />
              : <Code text={f.text} language={languageOf(path)} />}
      {f.truncated && <p className="t-label px-6 pb-5">文件太大，只显示开头 {bytes(f.text?.length ?? 0)}。</p>}
    </article>
  )
}

/** 代码：行号在一根细竖线左侧、钉在左边；正文高亮、不折行、横向滚 */
function Code({ text, language }: { text: string; language: string | null }) {
  const body = text.replace(/\n$/, '')
  const count = body === '' ? 1 : body.split('\n').length
  return (
    <div className="flex overflow-x-auto py-3 font-mono text-[0.75rem] leading-[1.7]">
      <div aria-hidden className="sticky left-0 shrink-0 border-r border-foreground/[0.08] bg-card pr-3 pl-6 text-right text-muted-foreground/45 tabular-nums select-none">
        {Array.from({ length: count }, (_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <pre className="hl m-0 pr-6 pl-4 whitespace-pre"><code dangerouslySetInnerHTML={{ __html: highlight(body, language) }} /></pre>
    </div>
  )
}

const NUMERIC = /^-?\d+(\.\d+)?(e[-+]?\d+)?$/i

function DataTable({ text, path }: { text: string; path: string }) {
  const { header, rows, more } = parseTable(text, path)
  const numeric = header.map((_, c) => rows.length > 0 && rows.every((row) => row[c] === undefined || row[c] === '' || NUMERIC.test(row[c])))
  return (
    <div className="px-6 py-3">
      <Table className="font-mono text-[0.75rem]">
        <TableHeader>
          <TableRow>{header.map((h, i) => <TableHead key={i} className={cn('whitespace-nowrap', numeric[i] && 'text-right')}>{h}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, r) => (
            <TableRow key={r}>{row.map((cell, c) => <TableCell key={c} className={cn('whitespace-nowrap', numeric[c] && 'text-right tabular-nums')}>{cell}</TableCell>)}</TableRow>
          ))}
        </TableBody>
      </Table>
      {more > 0 && <p className="t-label mt-3">还有 {more} 行。</p>}
    </div>
  )
}
