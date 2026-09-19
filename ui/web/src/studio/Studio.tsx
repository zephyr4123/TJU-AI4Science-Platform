// 编辑台：一张画布（React Flow，Dify 用的同一个引擎），一条线性的链——节点是研究阶段（装能力 + 参数）或断点，边只表示顺序
// （纲领 P-18；外层 #100 #101）。顶上一条阶段 / 断点 / 库，右边是选中节点的配置；边拼边问后端有没有问题（POST /workflows/check），
// 问题贴到节点上；存成 workflows/<name>.yaml。坐标不进文件，按顺序自动排、放不下换行。三张清单都从后端读，页面不写死。
// 左边那位助理每说完一轮 epoch 加一，库就重读——它可能刚存了一条。
import {
  Background, BackgroundVariant, Controls, type Edge, MarkerType, type Node, type OnSelectionChangeFunc, Panel, ReactFlow,
  ReactFlowProvider, useNodesState, useReactFlow,
} from '@xyflow/react'
import { SidebarSimple } from '@phosphor-icons/react'
import { type ChangeEvent, type DragEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '@/api/client'
import type { Capability, Workflow, WorkflowCheck } from '@/api/types'
import { ASSETS } from '@/assets'
import { ErrorNote, Problems, Skeleton } from '@/components/bits'
import SquishSwitch from '@/components/reactbits/SquishSwitch'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { coverageSentence } from '@/lib/stages'
import { useToken } from '@/lib/tokens'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { Inspector } from './Inspector'
import {
  type Draft, EMPTY, fromSeed, fromWorkflow, indexAt, insertAt, type Item, layout, moveTo, parseSeed, patch, problemIndices,
  remove, type Seed, SEED_MIME, toDraft, WIDTH,
} from './model'
import { StageNode, type StageNodeType, StopNode, type StopNodeType } from './nodes'
import { Ladder, Library } from './Palette'

import '@xyflow/react/dist/style.css'

type CanvasNode = StageNodeType | StopNodeType
/** 取景时给题头、梯子、右上角留出的空 */
const FIT = { top: '150px', left: '110px', right: '60px', bottom: '70px' } as const
const NODE_TYPES = { stage: StageNode, stop: StopNode }
type SetItems = (change: (items: Item[]) => Item[]) => void


interface ChatToggle { chatOpen: boolean; onToggleChat: () => void }

export function Studio({ epoch, ...chat }: { epoch: number } & ChatToggle) {
  const stages = useResource(api.stages, [])
  const workflows = useResource(api.workflows, [epoch])
  const catalog = useResource(api.capabilities, [])
  const loading = [stages, workflows, catalog].some((r) => r.loading && !r.data)
  const errors = [stages.error, workflows.error, catalog.error].filter((e): e is string => e !== null)
  if (loading) return <div className="p-6"><Skeleton lines={6} /></div>
  if (!stages.data || !workflows.data || !catalog.data) {
    return <div className="space-y-2 p-6">{errors.map((e) => <ErrorNote key={e} text={e} />)}</div>
  }
  return (
    <ReactFlowProvider>
      <Editor stages={stages.data} workflows={workflows.data} catalog={catalog.data} onSaved={() => void workflows.reload()} {...chat} />
    </ReactFlowProvider>
  )
}

function Editor({ stages, workflows, catalog, onSaved, ...chat }: {
  stages: string[]; workflows: Workflow[]; catalog: Capability[]; onSaved: () => void
} & ChatToggle) {
  const wide = useMediaQuery(WIDE)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [selected, setSelected] = useState<number | null>(null)
  const setItems: SetItems = useCallback((change) => setDraft((d) => ({ ...d, items: change(d.items) })), [])
  const titles = useMemo(() => new Map(catalog.map((c) => [c.name, c.title])), [catalog])

  // 边拼边查：形状同文件；空画布不问
  const doc = toDraft(draft)
  const key = JSON.stringify(doc.stages)
  const check = useResource(() => (draft.items.length ? api.checkWorkflow(doc) : Promise.resolve(null)), [key])
  const problems = check.data?.problems ?? []
  const perItem = useMemo(() => {
    const out = new Map<number, string[]>()
    for (const text of check.data?.problems ?? []) {
      for (const i of problemIndices(text)) out.set(i, [...(out.get(i) ?? []), text])
    }
    return out
  }, [check.data])

  const add = (seed: Seed, index = draft.items.length) => setItems((items) => insertAt(items, index, fromSeed(seed)))
  const load = (wf: Workflow) => { setDraft(fromWorkflow(wf)); setSelected(null) }
  const current = selected === null ? null : draft.items.find((it) => it.uid === selected) ?? null
  const inspector = current && (
    <Inspector key={current.uid} item={current} catalog={catalog}
               onChange={(next) => setItems((items) => patch(items, next.uid, () => next))} />
  )

  const taken = workflows.some((wf) => wf.name === draft.name.trim())
  return (
    <div className="relative h-full min-h-0">
      {/* 画布底下一层风景，压到只剩氛围；点阵铺在它上面 */}
      <Scene picture={ASSETS.studio} veil="mist" />
      <Canvas items={draft.items} titles={titles} perItem={perItem} selected={selected} onSelect={setSelected} setItems={setItems}
              onDrop={(seed, index) => add(seed, index)}>
        {/* 浮在画布上的几块：面板本身不挡鼠标，只有里面的东西接事件 */}
        <Panel position="top-left" className="pointer-events-none !m-3 flex items-start gap-3">
          <Button variant="ghost" size="icon-sm" onClick={chat.onToggleChat} aria-label={chat.chatOpen ? '收起对话' : '展开对话'}
                  className="pointer-events-auto hidden shrink-0 bg-card/70 backdrop-blur-sm lg:inline-flex">
            <SidebarSimple weight={chat.chatOpen ? 'fill' : 'regular'} />
          </Button>
          <div className="pointer-events-auto"><Ladder stages={stages} onAdd={(seed) => add(seed)} /></div>
          <div className="pointer-events-auto"><Heading draft={draft} setDraft={setDraft} /></div>
        </Panel>
        <Panel position="top-right" className="pointer-events-none !m-3 flex flex-col items-end gap-3">
          <div className="pointer-events-auto flex items-center gap-2">
            <Library workflows={workflows} onLoad={load} />
            <Save draft={draft} taken={taken} ok={draft.items.length > 0 && check.data !== null && problems.length === 0} onSaved={onSaved} />
          </div>
          {wide && inspector && (
            <div className="pointer-events-auto max-h-[calc(100dvh-13rem)] w-[19rem] overflow-y-auto rounded-2xl border bg-card/90 p-4 shadow-sm backdrop-blur-sm">{inspector}</div>
          )}
        </Panel>
        <Panel position="bottom-left" className="!m-3 max-w-[28rem]">
          <Verdict items={draft.items} check={check.data} error={check.error} />
        </Panel>
      </Canvas>
      {!wide && (
        <Sheet open={current !== null} onOpenChange={(open) => { if (!open) setSelected(null) }}>
          <SheetContent side="right" className="w-[20rem] overflow-y-auto p-5">
            <SheetHeader className="sr-only"><SheetTitle>配置</SheetTitle></SheetHeader>
            {inspector}
          </SheetContent>
        </Sheet>
      )}
    </div>
  )
}

/** 题头：像图纸的标题栏——宋体大标题、mono 名字、一行说明，都是填空线不是输入框 */
function Heading({ draft, setDraft }: { draft: Draft; setDraft: (f: (d: Draft) => Draft) => void }) {
  const field = (k: 'name' | 'title' | 'summary') => (e: ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }))
  return (
    <div className="pt-1">
      <input value={draft.title} onChange={field('title')} placeholder="标题" aria-label="标题" spellCheck={false}
             className="blank w-[20rem] font-serif text-[1.625rem] leading-tight font-semibold tracking-tight" />
      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <input value={draft.name} onChange={field('name')} placeholder="name" aria-label="name" spellCheck={false} autoComplete="off"
               className="blank w-[9rem] font-mono text-[0.8125rem]" />
        <span aria-hidden className="text-muted-foreground">·</span>
        <input value={draft.summary} onChange={field('summary')} placeholder="说明" aria-label="说明" spellCheck={false}
               className="blank w-[26rem] max-w-[calc(100vw-30rem)] text-[0.875rem]" />
      </div>
    </div>
  )
}

/** 右上角：保存；名字与库里的重了才出现「覆盖同名」的开关 */
function Save({ draft, taken, ok, onSaved }: { draft: Draft; taken: boolean; ok: boolean; onSaved: () => void }) {
  const [busy, setBusy] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const filled = draft.name.trim() !== '' && draft.title.trim() !== '' && draft.summary.trim() !== ''
  const save = async () => {
    setBusy(true)
    setNote(null)
    try {
      const saved = await api.saveWorkflow({ ...toDraft(draft), overwrite: taken && overwrite })
      setNote({ ok: true, text: `已存 ${saved.name}` })
      onSaved()
    } catch (exc) {
      setNote({ ok: false, text: exc instanceof Error ? exc.message : String(exc) })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex items-center gap-3">
      {note && <span className={cn('max-w-[20rem] truncate text-[0.8125rem]', note.ok ? 'text-ok' : 'text-bad')}>{note.text}</span>}
      {taken && (
        <label className="flex items-center gap-1.5 text-[0.8125rem] text-wait">
          覆盖同名<SquishSwitch checked={overwrite} onChange={setOverwrite} ariaLabel="覆盖同名" width={32} height={18} />
        </label>
      )}
      <Button size="sm" className="rounded-full px-4 shadow-sm" onClick={() => void save()} disabled={!ok || !filled || busy || (taken && !overwrite)}>
        {busy ? '保存中' : '保存'}
      </Button>
    </div>
  )
}

/** 左下角：检查结果。通过就说经过哪几个阶段；有问题一条一条列；提醒是琥珀色 */
function Verdict({ items, check, error }: { items: Item[]; check: WorkflowCheck | null; error: string | null }) {
  if (items.length === 0 || (!check && !error)) return null
  return (
    <div className="space-y-1.5 rounded-xl border bg-card/90 px-3 py-2 text-[0.8125rem] shadow-sm backdrop-blur-sm">
      {error && <ErrorNote text={error} />}
      {check && check.problems.length === 0 && <p className="text-ok">通过 · {coverageSentence(check.covers)}</p>}
      {check?.remarks.map((r) => <p key={r} className="text-wait">{r}</p>)}
      {check && <Problems items={check.problems} />}
    </div>
  )
}

// ── 画布 ──────────────────────────────────────────────────────────────────
function Canvas({ items, titles, perItem, selected, onSelect, setItems, onDrop, children }: {
  items: Item[]; titles: Map<string, string>; perItem: Map<number, string[]>
  selected: number | null; onSelect: (uid: number | null) => void
  setItems: SetItems; onDrop: (seed: Seed, index: number) => void
  children: ReactNode
}) {
  const { screenToFlowPosition, fitView } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([])
  const arrow = useToken('--muted-foreground')

  // 项 → 节点：位置按顺序排；选中态从上一版节点带过来，重排不丢
  useEffect(() => {
    const slots = layout(items)
    setNodes((prev) => {
      const was = new Set(prev.filter((n) => n.selected).map((n) => n.id))
      return items.map((item, i): CanvasNode => {
        const id = String(item.uid)
        const base = { id, position: { x: slots[i].x, y: slots[i].y }, selected: was.has(id) }
        const problems = perItem.get(i) ?? []
        const onRemove = () => setItems((all) => remove(all, item.uid))
        if (item.kind === 'stop') return { ...base, type: 'stop', data: { n: i + 1, note: item.note, problems, onRemove } }
        return { ...base, type: 'stage', data: { n: i + 1, stage: item.stage, caps: item.caps.map((p) => titles.get(p.cap) ?? p.cap), problems, onRemove } }
      })
    })
  }, [items, perItem, titles, setNodes, setItems])
  useEffect(() => {
    const id = requestAnimationFrame(() => void fitView({ padding: FIT, maxZoom: 1, duration: 200 }))
    return () => cancelAnimationFrame(id)
  }, [items.length, fitView])

  // 同一行左进右出；换行的那条从上一项底下出、下一项顶上进
  const edges = useMemo<Edge[]>(() => {
    const slots = layout(items)
    return items.slice(1).map((item, i) => {
      const wraps = slots[i + 1].row !== slots[i].row
      return {
        id: `${items[i].uid}-${item.uid}`, source: String(items[i].uid), target: String(item.uid), type: 'smoothstep',
        sourceHandle: wraps ? 'b' : 'r', targetHandle: wraps ? 't' : 'l', deletable: false, selectable: false, focusable: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: arrow },
      }
    })
  }, [items, arrow])

  const onSelectionChange: OnSelectionChangeFunc = useCallback(({ nodes: picked }) => {
    onSelect(picked.length === 1 ? Number(picked[0].id) : null)
  }, [onSelect])
  // 选中的项被删了（节点上的 ×、Backspace），面板跟着收
  useEffect(() => {
    if (selected !== null && !items.some((it) => it.uid === selected)) onSelect(null)
  }, [items, selected, onSelect])

  return (
    <ReactFlow<CanvasNode>
      nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} onNodesChange={onNodesChange} onSelectionChange={onSelectionChange}
      onNodeDragStop={(_, node: Node) => setItems((all) =>
        moveTo(all, Number(node.id), node.position.x + WIDTH[node.type as 'stage' | 'stop'] / 2, node.position.y + (node.measured?.height ?? 80) / 2))}
      onNodesDelete={(gone) => setItems((all) => all.filter((it) => !gone.some((n) => n.id === String(it.uid))))}
      onDragOver={(e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
      onDrop={(e: DragEvent) => {
        const seed = parseSeed(e.dataTransfer.getData(SEED_MIME))
        if (!seed) return
        e.preventDefault()
        const at = screenToFlowPosition({ x: e.clientX, y: e.clientY })
        onDrop(seed, indexAt(items, at.x, at.y))
      }}
      nodesConnectable={false} edgesFocusable={false} panOnScroll zoomOnScroll={false} minZoom={0.3} maxZoom={1.5}
      deleteKeyCode={['Backspace', 'Delete']} fitView fitViewOptions={{ padding: FIT, maxZoom: 1 }}
      className="!bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
      <Controls showInteractive={false} position="bottom-right" />
      {items.length === 0 && (
        <Panel position="top-center" className="pointer-events-none !mt-[28%]">
          <div className="grid h-[4.5rem] w-[13rem] place-items-center rounded-2xl border-2 border-dashed border-muted-foreground/40 font-serif text-[0.9375rem] text-muted-foreground">拖入阶段</div>
        </Panel>
      )}
      {children}
    </ReactFlow>
  )
}
