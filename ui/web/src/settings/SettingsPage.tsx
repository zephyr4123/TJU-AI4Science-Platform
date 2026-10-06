// 设置（纲领 P-25，外层 #134 #257）：地方栏里的一个地方，和首页、编辑台平级，整页铺在底图上（主人 2026-10-06：别再套一个悬浮窗；
// 原来那版太丑太普通，全面重做）。与首页同一套：标题一行（宋体「设置」、上次检查几时、检查全部），底下一张横纵结合的面板格——
// 宽屏两行两列、同一行的两块一样高：AI（冷色玻璃）| 算力；存放 | 外观。窄屏一列。
// AI：顶上两排滑块选助理、执行层各用哪家（改了只对之后开的对话生效，P-25），底下每家一格浅底：标、名、版本、正被谁用、状态、
// 模型、思考深度、检查——哪家、模型、深度只在这里改，对话框里没有（#257）。算力：一台一行，图标块 + 名字 + 状态与地址，动作靠右；
// 「添加」在块头，点了才在清单末尾展开。存放：三个数（项目、工作区、剩余空间）在上，三条路径在下。外观：三张缩略图选深浅色。
// 状态照旧是一枚点 + 一个词 + 几项数（过了的点外一圈心跳，没过静止的红点，没检查空心圈），没过时机器的原话小字一行。
// 键与开关沿用 reactbits 的改装件：「检查」CallChip、「移除」HoldButton（按住才算数）、两排滑块 RubberSegment、下拉 GlideSelect。
// 一切改动即刻写回按人的两份清单（`~/.config/ai4sci/`）。
import { ArrowsClockwise, Check, HardDrives, Laptop, Plus } from '@phosphor-icons/react'
import { type ReactNode, useCallback, useEffect, useState } from 'react'

import { api } from '@/api/client'
import type { AgentEntry, ComputeRow, SettingsDoc } from '@/api/types'
import { ASSETS } from '@/assets'
import { Aurora, type AuroraTone } from '@/components/Aurora'
import { BrandIcon } from '@/components/BrandIcon'
import { ErrorNote, Skeleton } from '@/components/bits'
import CallChip, { type CallChipStatus } from '@/components/reactbits/CallChip'
import GlideSelect from '@/components/reactbits/GlideSelect'
import HoldButton from '@/components/reactbits/HoldButton'
import RubberSegment from '@/components/reactbits/RubberSegment'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { type ThemeChoice, useThemeChoice } from '@/lib/theme'
import { cn } from '@/lib/utils'

import { agentStatus, computeStatus, parseSsh, shortVersion, type Status, suggestComputeName, tildify, type Tone } from './status'

// 两排滑块的前缀是名词（主人 2026-09-22：「对话用」是谓宾）：词表里一层叫「助理」、另一层叫「执行层」
const ROLES = [['chat', '助理'], ['executor', '执行层']] as const
const WORD_CLASS: Record<Tone, string> = { ok: 'text-ok', bad: 'text-bad', neutral: 'text-muted-foreground' }
/** 检查大概要跑多久（片上的底色填到九成用这么久）：一家底座 pong 一次几秒，全部一起十几秒 */
const CHECK_MS = 9000
const CHECK_ALL_MS = 16000

export function SettingsPage({ menu, onChanged }: {
  /** 窄屏页眉左端的地方清单入口 */
  menu?: ReactNode
  /** 检查过、改过设置：外面重读 /health 与每家新对话用的值，地方栏那个点跟着变 */
  onChanged: () => void
}) {
  const [doc, setDoc] = useState<SettingsDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  // 每个「检查」键上次跑完的结果：过了片洗铜绿、没过洗红；再按一次就重来
  const [results, setResults] = useState<Record<string, 'done' | 'error'>>({})

  useEffect(() => {
    api.settings().then(setDoc).catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
  }, [])

  /** 一个动作：忙着时整页的键都歇着，回来的整份替换掉，错了一句话摆在顶上；`judge` 看回来的那份这次算不算过 */
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
  const ctx: Ctx = { busy, chip, act }

  return (
    <div className="relative flex flex-1 flex-col overflow-y-auto">
      <Scene picture={ASSETS.backdrop} veil="mist" />
      <div className="relative mx-auto w-full max-w-[80rem] px-6 pt-8 pb-14 sm:px-8">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {menu}
          <h1 className="font-serif text-[1.75rem] leading-none font-semibold tracking-tight">设置</h1>
          <span className="text-[0.8125rem] text-muted-foreground tabular">{checkedAt(doc)}</span>
          <CallChip label="检查全部" status={chip('all')} expectedMs={CHECK_ALL_MS} disabled={!doc || busy !== null} className="ml-auto"
                    onPress={() => void act('all', () => api.runCheck('all'), allOk)} />
        </header>
        {error && <ErrorNote text={error} className="mt-5" />}
        {!doc && !error && <div className="mt-6"><Skeleton lines={8} /></div>}
        {doc && (
          <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Agents doc={doc} ctx={ctx} />
            <Computes doc={doc} ctx={ctx} />
            <Storage doc={doc} />
            <Look />
          </div>
        )}
      </div>
    </div>
  )
}

interface Ctx {
  busy: string | null
  chip: (key: string) => CallChipStatus
  act: (key: string, run: () => Promise<SettingsDoc>, judge?: (doc: SettingsDoc) => boolean) => Promise<void>
}

/** 全部检查算不算过：每家底座与每台算力上次检查都过了（本机不落盘、没记就算过） */
const allOk = (doc: SettingsDoc) =>
  doc.agents.entries.every((e) => e.last_check?.ok !== false) && doc.computes.every((c) => c.last_check?.ok !== false)

function checkedAt(doc: SettingsDoc | null): string {
  const stamps = (doc?.agents.entries ?? []).map((e) => e.last_check?.at).filter((s): s is string => !!s)
  if (!stamps.length) return '未检查'
  const latest = stamps.sort().at(-1)!
  return `上次检查 ${new Date(latest).toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
}

/** 一块面：块头一行（宋体名、一句淡字、右边动作），底下内容；面本身是首页那种玻璃 */
function Panel({ title, note, action, tone = 'quiet', children }: {
  title: string; note?: string; action?: ReactNode; tone?: AuroraTone; children: ReactNode
}) {
  return (
    <Aurora tone={tone} className="h-full">
      <section aria-label={title} className="flex h-full flex-col px-5 pt-4 pb-5 sm:px-6">
        <header className="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="font-serif text-[1.0625rem] font-semibold">{title}</h2>
          {note && <span className="text-[0.75rem] text-muted-foreground">{note}</span>}
          {action && <span className="ml-auto">{action}</span>}
        </header>
        <div className="mt-4 flex-1">{children}</div>
      </section>
    </Aurora>
  )
}

/** 脉冲点：过了是铜绿点外一圈慢慢扩开的心跳；没过是静止的红点；没检查是空心圈。字在旁边，点本身不读出来 */
function Pulse({ tone }: { tone: Tone }) {
  return (
    <span aria-hidden="true" className="relative inline-flex size-2.5 shrink-0 translate-y-px items-center justify-center self-center">
      {tone === 'ok' && <span className="absolute inset-0 rounded-full bg-ok/45 animate-pulse-ring motion-reduce:hidden" />}
      <span className={cn('relative size-2 rounded-full',
                          tone === 'ok' && 'bg-ok', tone === 'bad' && 'bg-bad',
                          tone === 'neutral' && 'ring-1 ring-inset ring-muted-foreground/70')} />
    </span>
  )
}

/** 一处状态：点 + 词 + 几项数一行，后面可以跟一段淡字（地址）；没过时机器的原话另起一行小字，长了截断、悬停看全 */
function StatusLine({ status, tail }: { status: Status; tail?: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <p className="flex min-w-0 items-baseline gap-2">
        <Pulse tone={status.tone} />
        <span className={cn('shrink-0 text-[0.8125rem] font-medium', WORD_CLASS[status.tone])}>{status.word}</span>
        {status.facts.map((fact) => <span key={fact} className="shrink-0 text-[0.75rem] text-muted-foreground tabular">{fact}</span>)}
        {tail && <span className="min-w-0 truncate text-[0.75rem] text-muted-foreground" title={tail}>{tail}</span>}
      </p>
      {status.hint && <p className="truncate pl-[1.125rem] text-[0.75rem] text-muted-foreground" title={status.hint}>{status.hint}</p>}
    </div>
  )
}

function Agents({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  const table = doc.agents
  const items = table.entries.map((e) => ({ value: e.name, label: e.title, icon: <BrandIcon name={e.name} className="size-3.5" /> }))
  return (
    <Panel title="AI" tone="cool" note="换哪家只对之后开的对话生效">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        {ROLES.map(([role, label]) => (
          <div key={role} className="flex items-center gap-2.5">
            <span className="text-[0.8125rem] text-muted-foreground">{label}</span>
            <RubberSegment aria-label={`${label}用哪家`} items={items} value={table[role]} size="md" radius={14} equalSlots={false}
                           disabled={ctx.busy !== null}
                           onChange={(name) => { if (name !== table[role]) void ctx.act(role, () => api.updateAgents({ [role]: name })) }} />
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {table.entries.map((entry) => (
          <AgentWell key={entry.name} entry={entry} ctx={ctx}
                     roles={ROLES.filter(([role]) => table[role] === entry.name).map(([, label]) => label)} />
        ))}
      </div>
    </Panel>
  )
}

/** 一家一格浅底：名字行（标、名、版本，检查靠右）、正被谁用、状态、模型与思考深度两行 */
function AgentWell({ entry, roles, ctx }: { entry: AgentEntry; roles: string[]; ctx: Ctx }) {
  const status = agentStatus(entry.last_check)
  const version = shortVersion(entry.last_check?.version)
  const tune = (key: 'model' | 'effort', value: string) => {
    if (value !== entry[key]) void ctx.act(`${entry.name}:${key}`, () => api.updateAgents({ agents: { [entry.name]: { [key]: value } } }))
  }
  return (
    <div className="flex flex-col gap-3.5 rounded-2xl bg-foreground/[0.03] p-4 ring-1 ring-inset ring-foreground/[0.05]">
      <div className="flex items-center gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.06)] ring-1 ring-foreground/[0.06]">
          <BrandIcon name={entry.name} className="size-[1.125rem]" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[0.9375rem] leading-tight font-semibold">{entry.title}</span>
          <span className="block text-[0.6875rem] text-muted-foreground tabular">{version ?? '版本未知'}</span>
        </span>
        <CallChip label="检查" status={ctx.chip(`check:${entry.name}`)} expectedMs={CHECK_MS} className="ml-auto" disabled={ctx.busy !== null}
                  onPress={() => void ctx.act(`check:${entry.name}`, () => api.runCheck('agents', entry.name),
                                              (next) => next.agents.entries.find((e) => e.name === entry.name)?.last_check?.ok === true)} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <StatusLine status={status} />
        {roles.length > 0 && (
          <span className="ml-auto flex gap-1">
            {roles.map((r) => <span key={r} className="rounded-full bg-primary/10 px-2 py-0.5 text-[0.6875rem] font-medium text-primary">{r}</span>)}
          </span>
        )}
      </div>
      <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-x-2 gap-y-2">
        <dt className="text-[0.8125rem] text-muted-foreground">模型</dt>
        <dd className="min-w-0">
          <GlideSelect ariaLabel={`${entry.title} 的模型`} value={entry.model} disabled={ctx.busy !== null}
                       options={entry.models.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                       onChange={(value) => tune('model', value)} />
        </dd>
        <dt className="text-[0.8125rem] text-muted-foreground">思考深度</dt>
        <dd className="min-w-0">
          <GlideSelect ariaLabel={`${entry.title} 的思考深度`} value={entry.effort} disabled={ctx.busy !== null}
                       options={entry.efforts.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                       onChange={(value) => tune('effort', value)} />
        </dd>
      </dl>
    </div>
  )
}

function Computes({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  const [adding, setAdding] = useState(false)
  return (
    <Panel title="算力" note={`${doc.computes.length} 台`}
           action={!adding && (
             <Button variant="outline" size="sm" className="rounded-full bg-card/70" disabled={ctx.busy !== null} onClick={() => setAdding(true)}>
               <Plus weight="bold" data-icon="inline-start" />添加
             </Button>
           )}>
      <ul className="space-y-4">
        {doc.computes.map((row) => <ComputeRowView key={row.name} row={row} ctx={ctx} />)}
      </ul>
      {adding && <AddCompute ctx={ctx} onDone={() => setAdding(false)} />}
    </Panel>
  )
}

/** 一台：图标块、名字（缺省那台带个字）、状态与地址一行，没过时机器的原话一行；检查与移除靠右 */
function ComputeRowView({ row, ctx }: { row: ComputeRow; ctx: Ctx }) {
  const status = computeStatus(row.last_check)
  const Icon = row.kind === 'local' ? Laptop : HardDrives
  return (
    <li className="flex items-start gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-foreground/[0.04] text-foreground/70 ring-1 ring-inset ring-foreground/[0.05]">
        <Icon weight="duotone" aria-hidden className="size-[1.125rem]" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="flex items-baseline gap-2">
          <span className="truncate text-[0.9375rem] font-semibold">{row.name}</span>
          {row.default && <span className="shrink-0 rounded-full bg-foreground/[0.06] px-1.5 py-px text-[0.6875rem] text-muted-foreground">缺省</span>}
        </p>
        <StatusLine status={status} tail={row.where} />
      </div>
      <span className="flex shrink-0 items-center gap-1.5">
        <CallChip label="检查" status={ctx.chip(`compute:${row.name}`)} expectedMs={CHECK_MS} disabled={ctx.busy !== null}
                  onPress={() => void ctx.act(`compute:${row.name}`, () => api.runCheck('computes', row.name),
                                              (next) => next.computes.find((c) => c.name === row.name)?.last_check?.ok !== false)} />
        {row.kind !== 'local' && (
          <HoldButton disabled={ctx.busy !== null} onHold={() => void ctx.act(`remove:${row.name}`, () => api.removeCompute(row.name))}>
            移除
          </HoldButton>
        )}
      </span>
    </li>
  )
}

/** 点了「添加」才展开：贴一行 ssh、密钥路径、名字；加完收回去 */
function AddCompute({ ctx, onDone }: { ctx: Ctx; onDone: () => void }) {
  const [line, setLine] = useState('')
  const [key, setKey] = useState('~/.ssh/id_ed25519')
  const [name, setName] = useState('')
  const ssh = parseSsh(line)
  const picked = name.trim() || (ssh ? suggestComputeName(ssh) : '')
  const ready = ssh !== null && key.trim() !== '' && picked !== '' && ctx.busy === null
  const add = () => {
    if (!ssh) return
    void ctx.act('compute:add', async () => {
      const next = await api.addCompute({ name: picked, ssh, key: key.trim() })
      onDone()
      return next
    })
  }
  return (
    <div className="mt-5 space-y-3 rounded-2xl bg-foreground/[0.03] p-4 ring-1 ring-inset ring-foreground/[0.05]">
      <Input value={line} onChange={(e) => setLine(e.target.value)} aria-label="ssh 一行" spellCheck={false} autoFocus
             placeholder="ssh -p 22 root@host" className="bg-card" />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <label className="space-y-1 text-[0.75rem] text-muted-foreground">
          <span>密钥</span>
          <Input value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false} aria-label="密钥路径" className="bg-card text-[0.875rem]" />
        </label>
        <label className="space-y-1 text-[0.75rem] text-muted-foreground">
          <span>名字</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} spellCheck={false} aria-label="机器的名字"
                 placeholder={ssh ? suggestComputeName(ssh) : ''} className="bg-card text-[0.875rem]" />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn('mr-auto text-[0.75rem]', line.trim() !== '' && ssh === null ? 'text-bad' : 'text-muted-foreground')}>
          {line.trim() !== '' && ssh === null ? '格式：user@host:port，或 ssh -p port user@host' : '仅密钥登录，公钥需已在远端'}
        </span>
        <Button variant="ghost" size="sm" disabled={ctx.busy !== null} onClick={onDone}>取消</Button>
        <Button size="sm" disabled={!ready} onClick={add}>
          {ctx.busy === 'compute:add' ? <ArrowsClockwise className="animate-spin" data-icon="inline-start" /> : <Plus weight="bold" data-icon="inline-start" />}添加
        </Button>
      </div>
    </div>
  )
}

/** 存放：三个数在上（项目、工作区、剩余空间，不可写时红字说出来），三条路径在下，家目录缩成 ~、悬停看全 */
function Storage({ doc }: { doc: SettingsDoc }) {
  const s = doc.storage
  const figures: [string, string, string?][] = [
    ['项目', `${s.projects}`, '个'], ['工作区', `${s.workspaces}`, '个'], ['剩余空间', `${Math.round(s.free_gb)}`, 'GB'],
  ]
  const paths: [string, string, string][] = [
    ['数据', s.home, s.writable ? '项目与对话' : '不可写'], ['设置', s.config, 'AI 与算力清单'], ['缓存', s.uv_cache, 'skill 环境'],
  ]
  return (
    <Panel title="存放">
      <dl className="grid grid-cols-3 gap-4">
        {figures.map(([label, value, unit]) => (
          <div key={label} className="min-w-0">
            <dt className="text-[0.75rem] text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 text-[1.375rem] leading-tight font-semibold tracking-tight tabular">
              {value}{unit && <span className="ml-0.5 text-[0.8125rem] font-medium text-muted-foreground">{unit}</span>}
            </dd>
          </div>
        ))}
      </dl>
      <dl className="mt-5 grid grid-cols-[3rem_minmax(0,1fr)] gap-x-3 gap-y-2.5">
        {paths.map(([label, path, what]) => (
          <div key={label} className="contents">
            <dt className="text-[0.8125rem] font-medium">{label}</dt>
            <dd className="min-w-0">
              <span className="block truncate text-[0.8125rem] tabular" title={path}>{tildify(path)}</span>
              <span className={cn('block text-[0.6875rem]', what === '不可写' ? 'text-bad' : 'text-muted-foreground')}>{what}</span>
            </dd>
          </div>
        ))}
      </dl>
    </Panel>
  )
}

// 三张缩略图画的是两套主题的样子：底色、卡片、字、靛——照 index.css 浅色与深色两段抄的示意色，只画缩略图，不是界面颜色
const SWATCH = {
  light: { bg: '#F5F6F8', card: '#FFFFFF', ink: '#1C2230', accent: '#2F4BC9' },
  dark: { bg: '#171A20', card: '#1E222A', ink: '#E6E8EE', accent: '#8FA3F5' },
} as const
const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'system', label: 'Auto' },
]

/** 外观：三张缩略图（浅、深、跟系统——左上浅右下深），点哪张用哪套；选中的描靛边、角上一枚勾 */
function Look() {
  const { choice, setChoice } = useThemeChoice()
  return (
    <Panel title="外观">
      <div role="radiogroup" aria-label="主题" className="grid grid-cols-3 gap-3">
        {THEMES.map((t) => {
          const on = t.value === choice
          return (
            <button key={t.value} type="button" role="radio" aria-checked={on} onClick={() => setChoice(t.value)}
                    className="group space-y-2 rounded-xl text-left outline-none">
              <span className={cn('relative block aspect-[4/3] overflow-hidden rounded-xl ring-1 transition-[box-shadow,transform] duration-200 ease-out group-hover:-translate-y-0.5 group-focus-visible:ring-2 group-focus-visible:ring-ring',
                                  on ? 'shadow-[0_8px_20px_-10px_color-mix(in_oklab,var(--primary)_60%,transparent)] ring-2 ring-primary' : 'ring-foreground/10')}>
                {t.value === 'system'
                  ? <><Thumb look="light" /><Thumb look="dark" className="[clip-path:polygon(100%_0,100%_100%,0_100%)]" /></>
                  : <Thumb look={t.value} />}
                {on && (
                  <span className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground shadow">
                    <Check weight="bold" className="size-3" />
                  </span>
                )}
              </span>
              <span className={cn('block text-center text-[0.8125rem]', on ? 'font-medium text-foreground' : 'text-muted-foreground')}>{t.label}</span>
            </button>
          )
        })}
      </div>
    </Panel>
  )
}

/** 一张缩略图：底色上一块卡片，卡片里一道靛色标题、两行字 */
function Thumb({ look, className }: { look: 'light' | 'dark'; className?: string }) {
  const c = SWATCH[look]
  return (
    <span aria-hidden="true" className={cn('absolute inset-0 p-[12%]', className)} style={{ background: c.bg }}>
      <span className="flex h-full flex-col gap-[9%] rounded-md p-[10%] shadow-sm" style={{ background: c.card }}>
        <span className="h-[14%] w-1/2 rounded-full" style={{ background: c.accent }} />
        <span className="h-[10%] w-4/5 rounded-full opacity-25" style={{ background: c.ink }} />
        <span className="h-[10%] w-3/5 rounded-full opacity-25" style={{ background: c.ink }} />
      </span>
    </span>
  )
}
