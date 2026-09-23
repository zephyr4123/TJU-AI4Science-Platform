// 编辑台：两个镜头（P-21，外层 #112）——「流程」是一张画布铺满整页（React Flow，Dify 用的同一个引擎），一条线性的链：节点是
// 研究阶段（装能力 + 参数）或断点，边只表示顺序（纲领 P-18；外层 #100 #101）；「能力」是按七个阶段陈列的能力清单与每个能力的
// 详情页（`Catalog`）。两个镜头都常驻只切显示，雾景与对话窗挂在外面，切换不闪。画布：左上角阶段梯与题头（玻璃板），右上角流程库、
// 保存与选中节点的配置；边拼边问后端有没有问题（POST /workflows/check），问题贴到节点上；存成 workflows/<name>.yaml，文件名由
// 标题生成（不显示、不让填）。坐标不进文件，按顺序自动排、放不下换行。流程助理的对话是右下角的悬浮窗，默认开着；它每说完一轮
// epoch 加一，流程库就重读。
import {
  Background, BackgroundVariant, type Edge, MarkerType, type Node, type OnSelectionChangeFunc, Panel, ReactFlow,
  ReactFlowProvider, useNodesState, useReactFlow,
} from '@xyflow/react'
import { ArrowsInLineHorizontal } from '@phosphor-icons/react'
import { type ChangeEvent, type DragEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '@/api/client'
import type { Capability, SkillEntry, StageInfo, Workflow, WorkflowCheck } from '@/api/types'
import { ASSETS } from '@/assets'
import { ErrorNote, Problems, Skeleton } from '@/components/bits'
import GlassSurface from '@/components/reactbits/GlassSurface'

import { useChatInset } from '@/chat/ChatPanel'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { suggestId } from '@/lib/slug'
import { coverageSentence } from '@/lib/stages'
import { useToken } from '@/lib/tokens'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { Catalog } from './Catalog'
import { Inspector } from './Inspector'
import {
  append, arranged, type Draft, dropAt, EMPTY, fromWorkflow, type Item, parseSeed, patch, place, positions, problemIndices,
  remove, type Seed, SEED_MIME, tidy, toDraft,
} from './model'
import { type CapChip, StageNode, type StageNodeType, StopNode, type StopNodeType } from './nodes'
import { Ladder, Library } from './Palette'

import '@xyflow/react/dist/style.css'

type CanvasNode = StageNodeType | StopNodeType
/** 取景时给题头、梯子、右上角留出的空 */
const FIT = { top: '150px', left: '110px', right: '60px', bottom: '70px' } as const
const NODE_TYPES = { stage: StageNode, stop: StopNode }
type SetItems = (change: (items: Item[]) => Item[]) => void
/** 编辑台的两个镜头：流程（画布）与能力（陈列与详情） */
export type StudioView = 'flow' | 'caps'


export function Studio({ epoch, view, focus, onFocus }: {
  epoch: number
  view: StudioView
  /** 「能力」镜头里打开的是哪个能力的详情（null 是陈列页）；从画布或配置板点名字过来时父组件同时切镜头 */
  focus: string | null
  onFocus: (name: string | null) => void
}) {
  const stages = useResource(api.stages, [], 'stages')
  const workflows = useResource(api.workflows, [epoch], 'workflows')
  const catalog = useResource(api.capabilities, [], 'caps')
  const skills = useResource(api.skills, [], 'skills')
  const loading = [stages, workflows, catalog, skills].some((r) => r.loading && !r.data)
  const errors = [stages.error, workflows.error, catalog.error, skills.error].filter((e): e is string => e !== null)
  if (loading) return <div className="flex-1 p-6"><Skeleton lines={6} /></div>
  if (!stages.data || !workflows.data || !catalog.data || !skills.data) {
    return <div className="flex-1 space-y-2 p-6">{errors.map((e) => <ErrorNote key={e} text={e} />)}</div>
  }
  return (
    <div className="relative min-h-0 min-w-0 flex-1">
      {/* 底下一层风景，压到只剩氛围；两个镜头共用，切换不重贴 */}
      <Scene picture={ASSETS.studio} veil="mist" />
      <div className={cn('relative h-full', view !== 'flow' && 'hidden')}>
        <ReactFlowProvider>
          <Editor stages={stages.data} workflows={workflows.data} catalog={catalog.data} skills={skills.data} onSaved={() => void workflows.reload()}
                  onOpenCap={onFocus} />
        </ReactFlowProvider>
      </div>
      <div className={cn('relative h-full', view !== 'caps' && 'hidden')}>
        <Catalog stages={stages.data} catalog={catalog.data} skills={skills.data} focus={focus} onFocus={onFocus} />
      </div>
    </div>
  )
}

function Editor({ stages, workflows, catalog, skills, onSaved, onOpenCap }: {
  stages: StageInfo[]; workflows: Workflow[]; catalog: Capability[]; skills: SkillEntry[]; onSaved: () => void; onOpenCap: (name: string) => void
}) {
  const wide = useMediaQuery(WIDE)
  const inset = useChatInset()  // 对话窗浮在右边时占掉的宽度：右上角那几块与底下的判词往左让
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [selected, setSelected] = useState<number | null>(null)
  const setItems: SetItems = useCallback((change) => setDraft((d) => ({ ...d, items: change(d.items) })), [])
  // 画布节点上的小片：步骤与 skill 都在一张表里，带 kind 让小片分得出来
  const chips = useMemo(() => new Map<string, CapChip>([
    ...catalog.map((c): [string, CapChip] => [c.name, { name: c.name, title: c.title, brief: c.brief, kind: '步骤' }]),
    ...skills.map((s): [string, CapChip] => [s.name, { name: s.name, title: s.title, brief: s.brief, kind: 'skill' }]),
  ]), [catalog, skills])

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

  const add = (seed: Seed) => setItems((items) => append(items, seed))
  const load = (wf: Workflow) => { setDraft(fromWorkflow(wf)); setSelected(null) }
  const current = selected === null ? null : draft.items.find((it) => it.uid === selected) ?? null
  const inspector = current && (
    <Inspector key={current.uid} item={current} catalog={catalog} skills={skills} onOpenCap={onOpenCap}
               onChange={(next) => setItems((items) => patch(items, next.uid, () => next))} />
  )

  return (
    <div className="relative h-full min-w-0">
      <Canvas items={draft.items} chips={chips} perItem={perItem} selected={selected} onSelect={setSelected} setItems={setItems} onOpenCap={onOpenCap}>
        {/* 浮在画布上的几块：面板本身不挡鼠标，只有里面的东西接事件 */}
        <Panel position="top-left" className="pointer-events-none !m-4 flex items-start gap-4">
          <div className="pointer-events-auto"><Ladder stages={stages.map((s) => s.name)} onAdd={(seed) => add(seed)} /></div>
          <div className="pointer-events-auto"><Heading draft={draft} setDraft={setDraft} /></div>
        </Panel>
        <Panel position="top-right" className="pointer-events-none !m-4 flex flex-col items-end gap-3" style={{ right: inset }}>
          <div className="pointer-events-auto flex items-center gap-2">
            {arranged(draft.items) && (
              <Button variant="outline" size="sm" className="rounded-full bg-card/85 backdrop-blur-sm" title="回到自动排列"
                      onClick={() => setItems(tidy)}>
                <ArrowsInLineHorizontal data-icon="inline-start" />排列
              </Button>
            )}
            <Library workflows={workflows} onLoad={load} onRemoved={onSaved} />
            <Save draft={draft} setDraft={setDraft} names={workflows.map((wf) => wf.name)}
                  ok={draft.items.length > 0 && check.data !== null && problems.length === 0} onSaved={onSaved} />
          </div>
          {wide && inspector && (
            <div className="pointer-events-auto max-h-[calc(100dvh-13rem)] w-[19rem] overflow-y-auto rounded-2xl border bg-card/90 p-4 shadow-sm backdrop-blur-sm">{inspector}</div>
          )}
        </Panel>
        <Panel position="bottom-center" className="!mb-4 max-w-[28rem]" style={{ left: `calc(50% - ${inset / 2}px)` }}>
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

/** 题头：一块玻璃板（与门口的输入框同款），上面是宋体大标题、一行说明——文字直接写在板上，没有框没有线。
 *  文件名不在这儿：由标题生成，不显示、不让填（P-21） */
const TEXT = 'w-full bg-transparent outline-none placeholder:text-muted-foreground/55'
function Heading({ draft, setDraft }: { draft: Draft; setDraft: (f: (d: Draft) => Draft) => void }) {
  const field = (k: 'title' | 'summary') => (e: ChangeEvent<HTMLInputElement>) =>
    setDraft((d) => ({ ...d, [k]: e.target.value }))
  return (
    <GlassSurface borderRadius={22} className="w-[34rem] max-w-[calc(100vw-24rem)] focus-within:ring-3 focus-within:ring-ring/35">
      <div className="px-5 pt-3.5 pb-3">
        <input value={draft.title} onChange={field('title')} placeholder="标题" aria-label="标题" spellCheck={false}
               className={cn(TEXT, 'font-serif text-[1.5rem] leading-tight font-semibold tracking-tight')} />
        <input value={draft.summary} onChange={field('summary')} placeholder="说明" aria-label="说明" spellCheck={false}
               className={cn(TEXT, 'mt-1 text-[0.875rem]')} />
      </div>
    </GlassSurface>
  )
}


/** 右上角：保存。从流程库载入的（或存过一次的）就是覆盖它自己；新拼的文件名从标题生成、避开库里已有的，所以没有「同名」这回事 */
function Save({ draft, setDraft, names, ok, onSaved }: {
  draft: Draft; setDraft: (f: (d: Draft) => Draft) => void; names: string[]; ok: boolean; onSaved: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const filled = draft.title.trim() !== '' && draft.summary.trim() !== ''
  const save = async () => {
    setBusy(true)
    setNote(null)
    const existing = draft.name.trim() !== ''
    const name = existing ? draft.name.trim() : suggestId(draft.title, names, new Date(), 'flow')
    try {
      const saved = await api.saveWorkflow({ ...toDraft({ ...draft, name }), overwrite: existing })
      setDraft((d) => ({ ...d, name: saved.name }))
      setNote({ ok: true, text: '已保存' })
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
      <Button size="sm" className="rounded-full px-4 shadow-sm" onClick={() => void save()} disabled={!ok || !filled || busy}>
        {busy ? '保存中' : '保存'}
      </Button>
    </div>
  )
}

/** 底下：检查结果。通过就说经过哪几个阶段；有问题一条一条列；提醒是琥珀色 */
function Verdict({ items, check, error }: { items: Item[]; check: WorkflowCheck | null; error: string | null }) {
  if (items.length === 0 || (!check && !error)) return null
  return (
    <div className="space-y-1.5 rounded-xl border bg-card/90 px-3 py-2 text-[0.8125rem] shadow-sm backdrop-blur-sm">
      {error && <ErrorNote text={error} />}
      {check && check.problems.length === 0 && <p className="text-ok">校验通过 · {coverageSentence(check.covers)}</p>}
      {check?.remarks.map((r) => <p key={r} className="text-wait">{r}</p>)}
      {check && <Problems items={check.problems} />}
    </div>
  )
}

// ── 画布 ──────────────────────────────────────────────────────────────────
function Canvas({ items, chips, perItem, selected, onSelect, setItems, onOpenCap, children }: {
  items: Item[]; chips: Map<string, CapChip>; perItem: Map<number, string[]>
  selected: number | null; onSelect: (uid: number | null) => void
  setItems: SetItems; onOpenCap: (name: string) => void
  children: ReactNode
}) {
  const { screenToFlowPosition, fitView } = useReactFlow()
  const inset = useChatInset()
  const padding = useMemo(() => ({ ...FIT, right: `${parseFloat(FIT.right) + inset}px` as const }), [inset])  // 取景避开浮着的对话窗
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([])
  const arrow = useToken('--muted-foreground')

  // 项 → 节点：摆过的在摆的地方、没摆过的自动排；选中态从上一版节点带过来，重排不丢
  useEffect(() => {
    const at = positions(items)
    setNodes((prev) => {
      const was = new Set(prev.filter((n) => n.selected).map((n) => n.id))
      return items.map((item, i): CanvasNode => {
        const id = String(item.uid)
        const base = { id, position: at[i], selected: was.has(id) }
        const problems = perItem.get(i) ?? []
        const onRemove = () => setItems((all) => remove(all, item.uid))
        if (item.kind === 'stop') return { ...base, type: 'stop', data: { n: i + 1, note: item.note, problems, onRemove } }
        const caps = item.caps.map((p) => chips.get(p.cap) ?? { name: p.cap, title: p.cap, brief: '', kind: '步骤' as const })
        return { ...base, type: 'stage', data: { n: i + 1, stage: item.stage, caps, problems, onRemove, onOpenCap } }
      })
    })
  }, [items, perItem, chips, setNodes, setItems, onOpenCap])
  useEffect(() => {
    const id = requestAnimationFrame(() => void fitView({ padding, maxZoom: 1, duration: 200 }))
    return () => cancelAnimationFrame(id)
  }, [items.length, fitView, padding])

  // 下一项在右边就左进右出；在下面（换行、或人摆到下面去了）就从上一项底下出、下一项顶上进
  const edges = useMemo<Edge[]>(() => {
    const at = positions(items)
    return items.slice(1).map((item, i) => {
      const wraps = at[i + 1].y - at[i].y > 60
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
      onNodeDragStop={(_, node: Node) => setItems((all) => place(all, Number(node.id), { x: node.position.x, y: node.position.y }))}
      onNodesDelete={(gone) => setItems((all) => all.filter((it) => !gone.some((n) => n.id === String(it.uid))))}
      onDragOver={(e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
      onDrop={(e: DragEvent) => {
        const seed = parseSeed(e.dataTransfer.getData(SEED_MIME))
        if (!seed) return
        e.preventDefault()
        const at = screenToFlowPosition({ x: e.clientX, y: e.clientY })
        setItems((all) => dropAt(all, seed, at.x, at.y))
      }}
      nodesConnectable={false} edgesFocusable={false} panOnScroll zoomOnScroll={false} minZoom={0.3} maxZoom={1.5} proOptions={{ hideAttribution: true }}
      deleteKeyCode={['Backspace', 'Delete']} fitView fitViewOptions={{ padding, maxZoom: 1 }}
      className="!bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
      {items.length === 0 && (
        <Panel position="top-center" className="pointer-events-none !mt-[28%]" style={{ left: `calc(50% - ${inset / 2}px)` }}>
          <div className="grid h-[4.5rem] w-[15rem] place-items-center rounded-2xl border-2 border-dashed border-muted-foreground/40 font-serif text-[0.9375rem] text-muted-foreground">从左栏拖入阶段</div>
        </Panel>
      )}
      {children}
    </ReactFlow>
  )
}
