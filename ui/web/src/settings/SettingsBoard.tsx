// 设置：压在当前地方上的一块悬浮板（纲领 P-25，外层 #134）。入口在地方栏的脚；底图照旧铺满，板四周留边、圆角、投影。
// 左边一列索引，右边一页滚下来，四段：AI（对话用 / 执行用两个下拉；每家一块——名字与版本、机器说的一句话、模型与深度、检查）、
// 算力（一张表；贴一行 ssh、密钥路径、添加）、存放（只看）、外观（浅 / 深 / 跟随系统）。状态是一句话不是徽章；没有序号、
// 没有全大写小标题、段与段之间不画框，靠索引与标题字重分段。一切改动即刻写回按人的两份清单（`~/.config/ai4sci/`）。
import { ArrowsClockwise, Plus, X } from '@phosphor-icons/react'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/api/client'
import type { AgentEntry, ComputeRow, SettingsDoc } from '@/api/types'
import { BrandIcon } from '@/components/BrandIcon'
import { ErrorNote, Skeleton } from '@/components/bits'
import GlideSelect from '@/components/reactbits/GlideSelect'
import { Button } from '@/components/ui/button'
import { type ThemeChoice, useThemeChoice } from '@/lib/theme'
import { cn } from '@/lib/utils'

import { agentSentence, computeSentence, parseSsh, suggestComputeName, type Tone } from './status'

const SECTIONS = [
  { id: 'ai', label: 'AI' },
  { id: 'compute', label: '算力' },
  { id: 'storage', label: '存放' },
  { id: 'look', label: '外观' },
] as const
type SectionId = (typeof SECTIONS)[number]['id']
const ROLE_LABEL = { chat: '对话用', executor: '执行用' } as const
const TONE_CLASS: Record<Tone, string> = { ok: 'text-ok', bad: 'text-bad', neutral: 'text-muted-foreground' }
const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: '浅' }, { value: 'dark', label: '深' }, { value: 'system', label: '跟随系统' },
]

interface Props {
  onClose: () => void
  /** 检查过、改过设置：外面重读 /health，地方栏那个点跟着变 */
  onChanged: () => void
}

export function SettingsBoard({ onClose, onChanged }: Props) {
  const [doc, setDoc] = useState<SettingsDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
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

  /** 一个动作：忙着时那段变灰，回来的整份替换掉，错了一句话摆在顶上 */
  const act = useCallback(async (key: string, run: () => Promise<SettingsDoc>) => {
    setBusy(key)
    setError(null)
    try {
      setDoc(await run())
      onChanged()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(null)
    }
  }, [onChanged])

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
          <Button variant="outline" size="sm" className="ml-auto" disabled={!doc || busy !== null}
                  onClick={() => void act('all', () => api.runCheck('all'))}>
            <ArrowsClockwise className={cn(busy === 'all' && 'animate-spin')} />检查全部
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭设置"><X /></Button>
        </header>
        <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-6 pb-16">
          {error && <ErrorNote text={error} className="mb-4" />}
          {!doc && !error && <Skeleton lines={6} />}
          {doc && (
            <div className="max-w-[44rem] space-y-12">
              <Agents doc={doc} busy={busy} act={act} />
              <Computes doc={doc} busy={busy} act={act} />
              <Storage doc={doc} />
              <Look />
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

type Act = (key: string, run: () => Promise<SettingsDoc>) => Promise<void>

function checkedAt(doc: SettingsDoc | null): string {
  const stamps = (doc?.agents.entries ?? []).map((e) => e.last_check?.at).filter((s): s is string => !!s)
  if (!stamps.length) return '还没检查过'
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

function Agents({ doc, busy, act }: { doc: SettingsDoc; busy: string | null; act: Act }) {
  const table = doc.agents
  const options = table.entries.map((e) => ({ value: e.name, label: e.title }))
  return (
    <Section id="ai" title="AI">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {(['chat', 'executor'] as const).map((role) => (
          <GlideSelect key={role} prefix={ROLE_LABEL[role]} ariaLabel={ROLE_LABEL[role]} options={options}
                       value={table[role]} disabled={busy !== null} size="md"
                       onChange={(name) => void act(role, () => api.updateAgents({ [role]: name }))} />
        ))}
        <span className="t-label basis-full">换了家只对之后开的对话生效，已经开的各用各的。</span>
      </div>
      <div className="space-y-8">
        {table.entries.map((entry) => <AgentBlock key={entry.name} entry={entry} busy={busy} act={act} />)}
      </div>
    </Section>
  )
}

function AgentBlock({ entry, busy, act }: { entry: AgentEntry; busy: string | null; act: Act }) {
  const sentence = agentSentence(entry.last_check)
  const version = entry.last_check?.version
  const tune = (key: 'model' | 'effort', value: string) =>
    void act(`${entry.name}:${key}`, () => api.updateAgents({ agents: { [entry.name]: { [key]: value } } }))
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <BrandIcon name={entry.name} className="size-5 shrink-0" />
        <span className="text-[1rem] font-medium">{entry.title}</span>
        {version && <span className="t-label">{version}</span>}
      </div>
      <p className={cn('t-body', TONE_CLASS[sentence.tone])}>{sentence.text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <GlideSelect prefix="模型" ariaLabel={`${entry.title} 的模型`} value={entry.model} disabled={busy !== null}
                     options={entry.models.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                     onChange={(value) => tune('model', value)} />
        <GlideSelect prefix="深度" ariaLabel={`${entry.title} 的思考深度`} value={entry.effort} disabled={busy !== null}
                     options={entry.efforts.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                     onChange={(value) => tune('effort', value)} />
        <Button variant="ghost" size="sm" className="ml-auto" disabled={busy !== null}
                onClick={() => void act(`check:${entry.name}`, () => api.runCheck('agents', entry.name))}>
          <ArrowsClockwise className={cn(busy === `check:${entry.name}` && 'animate-spin')} />检查
        </Button>
      </div>
    </div>
  )
}

function Computes({ doc, busy, act }: { doc: SettingsDoc; busy: string | null; act: Act }) {
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
      <div className="space-y-4">
        {doc.computes.map((row) => <ComputeLine key={row.name} row={row} busy={busy} act={act} />)}
      </div>
      <div className="space-y-2 pt-2">
        <div className="flex flex-wrap items-center gap-2">
          <input value={line} onChange={(e) => setLine(e.target.value)} aria-label="ssh 那一行" spellCheck={false}
                 placeholder="贴一行 ssh 命令，比如 ssh -p 22 root@主机"
                 className="min-w-[18rem] flex-1 rounded-lg bg-background px-3 py-2 text-[0.9375rem] ring-1 ring-foreground/10 placeholder:text-muted-foreground focus:ring-2 focus:ring-ring focus:outline-none" />
          <Button size="sm" disabled={!ready} onClick={add}>
            {busy === 'compute:add' ? <ArrowsClockwise className="animate-spin" /> : <Plus weight="bold" />}添加
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 text-[0.875rem] text-muted-foreground">
            密钥
            <input value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false} aria-label="密钥路径"
                   className="w-[14rem] rounded-md bg-background px-2 py-1 text-[0.875rem] text-foreground ring-1 ring-foreground/10 focus:ring-2 focus:ring-ring focus:outline-none" />
          </label>
          <label className="flex items-center gap-2 text-[0.875rem] text-muted-foreground">
            名字
            <input value={name} onChange={(e) => setName(e.target.value)} spellCheck={false} aria-label="机器的名字"
                   placeholder={ssh ? suggestComputeName(ssh) : ''}
                   className="w-[9rem] rounded-md bg-background px-2 py-1 text-[0.875rem] text-foreground ring-1 ring-foreground/10 placeholder:text-muted-foreground focus:ring-2 focus:ring-ring focus:outline-none" />
          </label>
          {line.trim() !== '' && ssh === null && <span className="t-label text-bad">这一行认不出：要有 user@主机，端口用 -p 或冒号</span>}
        </div>
        <p className="t-label">只认密钥，不收密码；公钥先贴到那台机器上。接上会就地探测，探不过也留着，用的时候再说。</p>
      </div>
    </Section>
  )
}

function ComputeLine({ row, busy, act }: { row: ComputeRow; busy: string | null; act: Act }) {
  const sentence = computeSentence(row.last_check)
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="text-[1rem] font-medium">{row.name}</span>
      <span className="t-label">{row.where}{row.default ? '，缺省' : ''}</span>
      <span className={cn('t-body basis-full sm:basis-auto', TONE_CLASS[sentence.tone])}>{sentence.text}</span>
      <span className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="sm" disabled={busy !== null}
                onClick={() => void act(`compute:${row.name}`, () => api.runCheck('computes', row.name))}>
          <ArrowsClockwise className={cn(busy === `compute:${row.name}` && 'animate-spin')} />检查
        </Button>
        {row.kind !== 'local' && (
          <Button variant="ghost" size="sm" disabled={busy !== null}
                  onClick={() => void act(`remove:${row.name}`, () => api.removeCompute(row.name))}>
            移除
          </Button>
        )}
      </span>
    </div>
  )
}

function Storage({ doc }: { doc: SettingsDoc }) {
  const s = doc.storage
  const rows: [string, string, string][] = [
    ['工作区', s.home, `${s.workspaces} 个，${s.writable ? '可写' : '不可写'}，剩 ${s.free_gb} GB`],
    ['设置', s.config, '算力与 AI 两份清单'],
    ['缓存', s.uv_cache, 'skill 脚本的环境'],
  ]
  return (
    <Section id="storage" title="存放">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3">
        {rows.map(([label, path, note]) => (
          <div key={label} className="contents">
            <dt className="t-label pt-0.5">{label}</dt>
            <dd className="min-w-0">
              <span className="block truncate text-[0.9375rem]" title={path}>{path}</span>
              <span className={cn('t-label', label === '工作区' && !s.writable && 'text-bad')}>{note}</span>
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
      <div role="radiogroup" aria-label="主题" className="inline-flex rounded-full bg-muted p-1">
        {THEMES.map((t) => (
          <button key={t.value} type="button" role="radio" aria-checked={choice === t.value} onClick={() => setChoice(t.value)}
                  className={cn('rounded-full px-4 py-1.5 text-[0.875rem] transition-colors',
                                choice === t.value ? 'bg-card font-medium text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
            {t.label}
          </button>
        ))}
      </div>
    </Section>
  )
}
