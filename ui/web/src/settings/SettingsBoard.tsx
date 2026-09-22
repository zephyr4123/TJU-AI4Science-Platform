// 设置：压在当前地方上的一块悬浮板（纲领 P-25，外层 #134）。入口在地方栏的脚；底图照旧铺满，板四周留边、圆角、投影。
// 左边一列索引，右边一页滚下来，四段：AI（助理 / 执行层两个下拉；每家一块——名字与版本、状态、模型与深度、检查）、
// 算力（一行一台；贴一行 ssh、密钥路径、添加）、存放（只看）、外观（浅 / 深 / 跟随系统）。
// 字按主人 2026-09-22 的要求：能用词就用词，短句也少，解释只留一行；状态是一枚脉冲点 + 一个词 + 几项数
// （过了的点外有一圈心跳，没过是静止的红点，没检查是空心圈），没过时机器的原话小字单独一行。
// 键与开关是 reactbits 的改装件（主人 2026-09-22：手搓的键一股 AI 味）：「检查」是 CallChip（按下去底色慢慢填、毫秒跳、过了洗铜绿、
// 没过洗红抖一下）、「移除」是 HoldButton（按住涨满才算数）、外观三档是 RubberSegment（橡皮滑块）；输入框用 shadcn 的 Input。
// 没有序号、没有全大写小标题、段与段之间不画框，靠索引与标题字重分段。一切改动即刻写回按人的两份清单（`~/.config/ai4sci/`）。
import { ArrowsClockwise, Plus, X } from '@phosphor-icons/react'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/api/client'
import type { AgentEntry, ComputeRow, SettingsDoc } from '@/api/types'
import { BrandIcon } from '@/components/BrandIcon'
import { ErrorNote, Skeleton } from '@/components/bits'
import CallChip, { type CallChipStatus } from '@/components/reactbits/CallChip'
import GlideSelect from '@/components/reactbits/GlideSelect'
import HoldButton from '@/components/reactbits/HoldButton'
import RubberSegment from '@/components/reactbits/RubberSegment'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { type ThemeChoice, useThemeChoice } from '@/lib/theme'
import { cn } from '@/lib/utils'

import { agentStatus, computeStatus, parseSsh, shortVersion, type Status, suggestComputeName, type Tone } from './status'

const SECTIONS = [
  { id: 'ai', label: 'AI' },
  { id: 'compute', label: '算力' },
  { id: 'storage', label: '存放' },
  { id: 'look', label: '外观' },
] as const
type SectionId = (typeof SECTIONS)[number]['id']
// 两个下拉的前缀是名词（主人 2026-09-22：「对话用」是谓宾）：门里那枚旋钮也叫「助理」，词表里另一层叫「执行层」
const ROLE_LABEL = { chat: '助理', executor: '执行层' } as const
const WORD_CLASS: Record<Tone, string> = { ok: 'text-ok', bad: 'text-bad', neutral: 'text-muted-foreground' }
const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: '浅' }, { value: 'dark', label: '深' }, { value: 'system', label: '跟随系统' },
]
/** 检查大概要跑多久（片上的底色填到九成用这么久）：一家底座 pong 一次几秒，全部一起十几秒 */
const CHECK_MS = 9000
const CHECK_ALL_MS = 16000

interface Props {
  onClose: () => void
  /** 检查过、改过设置：外面重读 /health，地方栏那个点跟着变 */
  onChanged: () => void
}

export function SettingsBoard({ onClose, onChanged }: Props) {
  const [doc, setDoc] = useState<SettingsDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  // 每个「检查」键上次跑完的结果：过了片洗铜绿、没过洗红；再按一次就重来
  const [results, setResults] = useState<Record<string, 'done' | 'error'>>({})
  const [active, setActive] = useState<SectionId>('ai')
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.settings().then(setDoc).catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
  }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  /** 一个动作：忙着时那段变灰，回来的整份替换掉，错了一句话摆在顶上；`judge` 看回来的那份这次算不算过（检查跑完了但没过也是「没过」） */
  const act = useCallback(async (key: string, run: () => Promise<SettingsDoc>, judge?: (doc: SettingsDoc) => boolean) => {
    setBusy(key)
    setError(null)
    try {
      const next = await run()
      setDoc(next)
      setResults((r) => ({ ...r, [key]: judge && !judge(next) ? 'error' : 'done' }))
      onChanged()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
      setResults((r) => ({ ...r, [key]: 'error' }))
    } finally {
      setBusy(null)
    }
  }, [onChanged])
  const chip = (key: string): CallChipStatus => (busy === key ? 'running' : results[key] ?? 'idle')

  const jump = (id: SectionId) => {
    setActive(id)
    document.getElementById(`settings-${id}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }
  // 索引随滚动亮：过了视口上方四成的最后一段；滚到底就是最后一段（短的一页最后几段永远到不了顶）
  const onScroll = () => {
    const box = scroller.current
    if (!box) return
    if (box.scrollTop + box.clientHeight >= box.scrollHeight - 2) {
      setActive(SECTIONS[SECTIONS.length - 1].id)
      return
    }
    const line = box.getBoundingClientRect().top + box.clientHeight * 0.4
    let current: SectionId = 'ai'
    for (const { id } of SECTIONS) {
      const el = document.getElementById(`settings-${id}`)
      if (el && el.getBoundingClientRect().top <= line) current = id
    }
    setActive(current)
  }

  return (
    <section aria-label="设置"
             className="absolute inset-3 z-30 flex overflow-hidden rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_24px_56px_-24px_rgb(0_0_0/0.35)] ring-1 ring-foreground/[0.06]">
      <nav aria-label="设置的几段" className="hidden w-[9rem] shrink-0 flex-col gap-1 border-r px-3 pt-16 sm:flex">
        {SECTIONS.map((s) => (
          <button key={s.id} type="button" onClick={() => jump(s.id)}
                  className={cn('rounded-md px-3 py-1.5 text-left text-[0.9375rem] transition-colors',
                                active === s.id ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground hover:text-foreground')}>
            {s.label}
          </button>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 px-6">
          <span className="font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">设置</span>
          <span className="t-label hidden sm:inline">{checkedAt(doc)}</span>
          <CallChip label="检查全部" status={chip('all')} expectedMs={CHECK_ALL_MS} className="ml-auto" disabled={!doc || busy !== null}
                    onPress={() => void act('all', () => api.runCheck('all'), allOk)} />
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭设置"><X /></Button>
        </header>
        <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-6 pb-16">
          {error && <ErrorNote text={error} className="mb-4" />}
          {!doc && !error && <Skeleton lines={6} />}
          {doc && (
            <div className="max-w-[44rem] space-y-12">
              <Agents doc={doc} busy={busy} chip={chip} act={act} />
              <Computes doc={doc} busy={busy} chip={chip} act={act} />
              <Storage doc={doc} />
              <Look />
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

type Act = (key: string, run: () => Promise<SettingsDoc>, judge?: (doc: SettingsDoc) => boolean) => Promise<void>
type Chip = (key: string) => CallChipStatus

/** 全部检查算不算过：每家底座与每台算力上次检查都过了（本机不落盘、没记就算过） */
const allOk = (doc: SettingsDoc) =>
  doc.agents.entries.every((e) => e.last_check?.ok !== false) && doc.computes.every((c) => c.last_check?.ok !== false)

function checkedAt(doc: SettingsDoc | null): string {
  const stamps = (doc?.agents.entries ?? []).map((e) => e.last_check?.at).filter((s): s is string => !!s)
  if (!stamps.length) return '未检查'
  const latest = stamps.sort().at(-1)!
  return `上次检查 ${new Date(latest).toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
}

function Section({ id, title, children }: { id: SectionId; title: string; children: ReactNode }) {
  return (
    <section id={`settings-${id}`} aria-labelledby={`settings-${id}-title`} className="scroll-mt-4 space-y-5">
      <h2 id={`settings-${id}-title`} className="t-step">{title}</h2>
      {children}
    </section>
  )
}

/** 脉冲点：过了是铜绿点外一圈慢慢扩开的心跳；没过是静止的红点；没检查是空心圈。字在旁边，点本身不读出来 */
function Pulse({ tone }: { tone: Tone }) {
  return (
    <span aria-hidden="true" className="relative inline-flex size-2.5 shrink-0 items-center justify-center">
      {tone === 'ok' && <span className="absolute inset-0 rounded-full bg-ok/45 animate-pulse-ring motion-reduce:hidden" />}
      <span className={cn('relative size-2 rounded-full',
                          tone === 'ok' && 'bg-ok', tone === 'bad' && 'bg-bad',
                          tone === 'neutral' && 'ring-1 ring-inset ring-muted-foreground/70')} />
    </span>
  )
}

/** 一处状态：点 + 词 + 几项数一行；没过时机器的原话单独一行小字，长了截断、悬停看全 */
function StatusLine({ status, className, hintClassName }: { status: Status; className?: string; hintClassName?: string }) {
  return (
    <>
      <span className={cn('inline-flex items-center gap-2 text-[0.875rem]', className)}>
        <Pulse tone={status.tone} />
        <span className={cn('font-medium', WORD_CLASS[status.tone])}>{status.word}</span>
        {status.facts.map((fact) => <span key={fact} className="text-muted-foreground tabular-nums">{fact}</span>)}
      </span>
      {status.hint && <span className={cn('t-label block truncate', hintClassName)} title={status.hint}>{status.hint}</span>}
    </>
  )
}

function Agents({ doc, busy, chip, act }: { doc: SettingsDoc; busy: string | null; chip: Chip; act: Act }) {
  const table = doc.agents
  const options = table.entries.map((e) => ({ value: e.name, label: e.title }))
  return (
    <Section id="ai" title="AI">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {(['chat', 'executor'] as const).map((role) => (
          <GlideSelect key={role} prefix={ROLE_LABEL[role]} ariaLabel={ROLE_LABEL[role]} options={options}
                       value={table[role]} disabled={busy !== null} size="md"
                       onChange={(name) => void act(role, () => api.updateAgents({ [role]: name }))} />
        ))}
        <span className="t-label">仅对新对话生效</span>
      </div>
      <div className="space-y-8">
        {table.entries.map((entry) => <AgentBlock key={entry.name} entry={entry} busy={busy} chip={chip} act={act} />)}
      </div>
    </Section>
  )
}

function AgentBlock({ entry, busy, chip, act }: { entry: AgentEntry; busy: string | null; chip: Chip; act: Act }) {
  const status = agentStatus(entry.last_check)
  const version = shortVersion(entry.last_check?.version)
  const tune = (key: 'model' | 'effort', value: string) =>
    void act(`${entry.name}:${key}`, () => api.updateAgents({ agents: { [entry.name]: { [key]: value } } }))
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <BrandIcon name={entry.name} className="size-5 shrink-0" />
        <span className="text-[1rem] font-medium">{entry.title}</span>
        {version && <span className="t-label tabular-nums">{version}</span>}
        <CallChip label="检查" status={chip(`check:${entry.name}`)} expectedMs={CHECK_MS} className="ml-auto" disabled={busy !== null}
                  onPress={() => void act(`check:${entry.name}`, () => api.runCheck('agents', entry.name),
                                          (next) => next.agents.entries.find((e) => e.name === entry.name)?.last_check?.ok === true)} />
      </div>
      <div className="space-y-1 pl-8">
        <StatusLine status={status} />
      </div>
      <div className="flex flex-wrap items-center gap-2 pl-8">
        <GlideSelect prefix="模型" ariaLabel={`${entry.title} 的模型`} value={entry.model} disabled={busy !== null}
                     options={entry.models.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                     onChange={(value) => tune('model', value)} />
        <GlideSelect prefix="深度" ariaLabel={`${entry.title} 的思考深度`} value={entry.effort} disabled={busy !== null}
                     options={entry.efforts.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                     onChange={(value) => tune('effort', value)} />
      </div>
    </div>
  )
}

function Computes({ doc, busy, chip, act }: { doc: SettingsDoc; busy: string | null; chip: Chip; act: Act }) {
  const [line, setLine] = useState('')
  const [key, setKey] = useState('~/.ssh/id_ed25519')
  const [name, setName] = useState('')
  const ssh = parseSsh(line)
  const picked = name.trim() || (ssh ? suggestComputeName(ssh) : '')
  const ready = ssh !== null && key.trim() !== '' && picked !== '' && busy === null
  const add = () => {
    if (!ssh) return
    void act('compute:add', async () => {
      const next = await api.addCompute({ name: picked, ssh, key: key.trim() })
      setLine('')
      setName('')
      return next
    })
  }
  return (
    <Section id="compute" title="算力">
      <div className="space-y-3">
        {doc.computes.map((row) => <ComputeLine key={row.name} row={row} busy={busy} chip={chip} act={act} />)}
      </div>
      <div className="space-y-2 pt-2">
        <div className="flex flex-wrap items-center gap-2">
          <Input value={line} onChange={(e) => setLine(e.target.value)} aria-label="ssh 一行" spellCheck={false}
                 placeholder="ssh -p 22 root@host" className="min-w-[18rem] flex-1 bg-background" />
          <Button size="sm" disabled={!ready} onClick={add}>
            {busy === 'compute:add' ? <ArrowsClockwise className="animate-spin" /> : <Plus weight="bold" />}添加
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 text-[0.875rem] text-muted-foreground">
            密钥
            <Input value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false} aria-label="密钥路径"
                   className="h-7 w-[14rem] bg-background text-[0.875rem]" />
          </label>
          <label className="flex items-center gap-2 text-[0.875rem] text-muted-foreground">
            名字
            <Input value={name} onChange={(e) => setName(e.target.value)} spellCheck={false} aria-label="机器的名字"
                   placeholder={ssh ? suggestComputeName(ssh) : ''} className="h-7 w-[9rem] bg-background text-[0.875rem]" />
          </label>
          {line.trim() !== '' && ssh === null && <span className="t-label text-bad">格式：user@host:port，或 ssh -p port user@host</span>}
        </div>
        <p className="t-label">仅密钥登录，公钥需已在远端</p>
      </div>
    </Section>
  )
}

function ComputeLine({ row, busy, chip, act }: { row: ComputeRow; busy: string | null; chip: Chip; act: Act }) {
  const status = computeStatus(row.last_check)
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-x-3">
        <span className="w-16 shrink-0 truncate text-[1rem] font-medium" title={row.name}>{row.name}</span>
        <span className="t-label min-w-0 truncate" title={row.where}>{row.where}</span>
        {row.default && <span className="t-label shrink-0 rounded-md bg-muted px-1.5 py-0.5 leading-none">缺省</span>}
        <StatusLine status={{ ...status, hint: undefined }} className="ml-auto shrink-0" />
        <span className="flex shrink-0 items-center gap-1.5">
          <CallChip label="检查" status={chip(`compute:${row.name}`)} expectedMs={CHECK_MS} disabled={busy !== null}
                    onPress={() => void act(`compute:${row.name}`, () => api.runCheck('computes', row.name),
                                            (next) => next.computes.find((c) => c.name === row.name)?.last_check?.ok !== false)} />
          {row.kind !== 'local' && (
            <HoldButton disabled={busy !== null} onHold={() => void act(`remove:${row.name}`, () => api.removeCompute(row.name))}>
              移除
            </HoldButton>
          )}
        </span>
      </div>
      {status.hint && <p className="t-label truncate pl-[4.75rem]" title={status.hint}>{status.hint}</p>}
    </div>
  )
}

function Storage({ doc }: { doc: SettingsDoc }) {
  const s = doc.storage
  const rows: [string, string, string[]][] = [
    ['工作区', s.home, [`${s.workspaces} 个`, s.writable ? '可写' : '不可写', `余 ${Math.round(s.free_gb)} GB`]],
    ['设置', s.config, ['AI 与算力清单']],
    ['缓存', s.uv_cache, ['skill 环境']],
  ]
  return (
    <Section id="storage" title="存放">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3">
        {rows.map(([label, path, facts]) => (
          <div key={label} className="contents">
            <dt className="t-label pt-0.5">{label}</dt>
            <dd className="min-w-0">
              <span className="block truncate text-[0.9375rem]" title={path}>{path}</span>
              <span className={cn('t-label flex gap-3 tabular-nums', label === '工作区' && !s.writable && 'text-bad')}>
                {facts.map((f) => <span key={f}>{f}</span>)}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}

function Look() {
  const { choice, setChoice } = useThemeChoice()
  return (
    <Section id="look" title="外观">
      <RubberSegment aria-label="主题" items={THEMES} value={choice} size="sm" radius={14} equalSlots={false}
                     onChange={(value) => setChoice(value as ThemeChoice)} />
    </Section>
  )
}
