// 设置（纲领 P-25，外层 #134 #268）：照 Claude 应用的设置窗（主人 2026-10-06 晚：分块太多每块都挤，结构与交互照它学，
// 样式跟全站）。点地方栏的「设置」不换地方，弹一个玻璃大窗：左栏按分类列——常规；AI 下每家一项；能力下文献检索；
// 平台下算力、存放——点一项右边出那一页，页里按小标题分节、一项一行（`kit.tsx`）。哪项上次检查没过，项后一枚红点。
// 窄屏窗铺满，先是分类清单，点进去一页，左上「‹ 设置」回清单。一切改动即刻写回平台的家里的清单（外层 #263）。
// 页面一起来就取的那一份也给「助理还不能说话」那扇窗（`KeyPrompt`，外层 #282）：助理那家缺 key 时弹，设置窗开着时不弹；
// 切回窗口时重读一份，key 在页面外面填好了窗自己关。
import { Books, CaretLeft, CaretRight, Database, GearSix, HardDrives, X } from '@phosphor-icons/react'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { type ReactNode, useCallback, useEffect, useState } from 'react'

import { api } from '@/api/client'
import type { SettingsDoc } from '@/api/types'
import { BrandIcon } from '@/components/BrandIcon'
import { ErrorNote, Skeleton } from '@/components/bits'
import { GLASS } from '@/components/glass'
import type { CallChipStatus } from '@/components/reactbits/CallChip'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogOverlay, DialogPortal, DialogTitle } from '@/components/ui/dialog'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

import { AgentPage } from './AgentPage'
import { Computes } from './Computes'
import { General } from './General'
import { KeyPrompt } from './KeyPrompt'
import type { Ctx } from './kit'
import { Literature } from './Literature'
import { ROLES } from './status'
import { Storage } from './Storage'

/** 宽到放得下左栏 + 一页：两栏；再窄就先清单后一页 */
const SPLIT = '(min-width: 48rem)'

type PageId = 'general' | 'literature' | 'computes' | 'storage' | `agent:${string}`
interface Item { id: PageId; label: string; icon: ReactNode; bad?: boolean }
interface Group { title?: string; items: Item[] }

const ICON = 'size-[1.125rem]'

/** 左栏：后面加一类设置就是这里加一项、加一页 */
function groups(doc: SettingsDoc | null): Group[] {
  return [
    { items: [{ id: 'general', label: '常规', icon: <GearSix className={ICON} /> }] },
    { title: 'AI', items: (doc?.agents.entries ?? []).map((e) => ({
      id: `agent:${e.name}` as const, label: e.title, icon: <BrandIcon name={e.name} className={ICON} />, bad: e.last_check?.ok === false,
    })) },
    { title: '能力', items: [{ id: 'literature', label: '文献检索', icon: <Books className={ICON} /> }] },
    { title: '平台', items: [
      { id: 'computes', label: '算力', icon: <HardDrives className={ICON} />, bad: doc?.computes.some((c) => c.last_check?.ok === false) },
      { id: 'storage', label: '存放', icon: <Database className={ICON} /> },
    ] },
  ]
}

/** 下拉的菜单挂在 body 上（GlideSelect），在窗外：点它不算点到窗外 */
const keepMenus = (e: Event) => {
  if ((e.target as Element | null)?.closest?.('[role="listbox"]')) e.preventDefault()
}

export function Settings({ open, onOpenChange, onChanged }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 检查过、改过设置：外面重读 /health 与每家新对话用的值，地方栏那个点跟着变 */
  onChanged: () => void
}) {
  const [doc, setDoc] = useState<SettingsDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  // 每个「检查」键上次跑完的结果：过了片洗铜绿、没过洗红；再按一次就重来
  const [results, setResults] = useState<Record<string, 'done' | 'error'>>({})
  const [page, setPage] = useState<PageId>('general')
  const split = useMediaQuery(SPLIT)
  const [inside, setInside] = useState(false)

  // 页面一起来就先取一份，点开时已经在手上；每次打开再重读（上次那份先摆着，不闪）
  const reload = useCallback(() => {
    api.settings().then((next) => { setDoc(next); setError(null) }).catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
  }, [])
  useEffect(reload, [open, reload])
  // 切回这个窗口也重读：四种用法共用一份后端，key 可能刚在终端里（`ai4sci setup`）或另一个页面里填过，弹着的窗该自己关
  useEffect(() => {
    const back = () => { if (!document.hidden) reload() }
    window.addEventListener('focus', back)
    document.addEventListener('visibilitychange', back)
    return () => {
      window.removeEventListener('focus', back)
      document.removeEventListener('visibilitychange', back)
    }
  }, [reload])

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
  // 「助理还不能说话」那扇窗：没检查过时后台探一次助理那家。不走 act：不锁设置里的键、不记进「检查」片（人没按它）；
  // 探着的时候那扇窗先不弹。试通回来的整份换上，检查片都回到没按过（通了还挂着上次的红）
  const [probing, setProbing] = useState(false)
  const probe = useCallback((agent: string) => {
    setProbing(true)
    api.runCheck('agents', agent).then((next) => { setDoc(next); onChanged() })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)))
      .finally(() => setProbing(false))
  }, [onChanged])
  const quickstarted = useCallback((next: SettingsDoc) => { setDoc(next); setResults({}); onChanged() }, [onChanged])
  const [asked, setAsked] = useState(0)
  const askKey = useCallback(() => { onOpenChange(false); setAsked((n) => n + 1) }, [onOpenChange])
  const ctx: Ctx = { busy, chip, act, askKey }

  const all = groups(doc)
  const current = all.flatMap((g) => g.items).find((item) => item.id === page)
  const pick = (id: PageId) => { setPage(id); setInside(true) }
  const showList = split || !inside
  const showPage = split || inside

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => { onOpenChange(next); if (!next) setInside(false) }}>
        <DialogPortal>
          <DialogOverlay />
          {/* 只淡入不缩放（Claude 的设置窗也是）：缩放中挂上的分段开关会量成缩小后的尺寸 */}
          <DialogPrimitive.Content aria-describedby={undefined} onInteractOutside={keepMenus}
                                   className={cn('fixed top-1/2 left-1/2 z-50 flex h-[min(46rem,calc(100dvh-2rem))] w-[min(62rem,calc(100vw-1.5rem))] -translate-1/2 overflow-hidden rounded-[28px] text-sm outline-none',
                                                 'duration-200 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0',
                                                 GLASS, 'shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.06),0_28px_72px_-18px_rgb(0_0_0/0.38)]')}>
            {showList && (
              <nav aria-label="设置的分类"
                   className={cn('flex shrink-0 flex-col overflow-y-auto px-3 pb-4', split ? 'w-[15rem] border-r border-foreground/[0.06] bg-foreground/[0.025]' : 'flex-1')}>
                <div className="flex items-center pt-6 pr-1 pb-2 pl-3">
                  <DialogTitle className="font-serif text-[1.375rem] leading-none font-semibold">设置</DialogTitle>
                  {!split && <Close />}
                </div>
                {all.map((group, i) => (
                  <div key={group.title ?? i} className="mt-3">
                    {group.title && <p className="px-3 pt-2 pb-1.5 text-[0.75rem] text-muted-foreground">{group.title}</p>}
                    {group.items.map((item) => (
                      <NavRow key={item.id} item={item} active={split && item.id === page} chevron={!split} onClick={() => pick(item.id)} />
                    ))}
                  </div>
                ))}
              </nav>
            )}
            {showPage && (
              <div className="relative flex min-w-0 flex-1 flex-col">
                <div className="flex h-14 shrink-0 items-center gap-1 px-3">
                  {!split && (
                    <Button variant="ghost" size="sm" className="rounded-full text-muted-foreground" onClick={() => setInside(false)}>
                      <CaretLeft data-icon="inline-start" />设置
                    </Button>
                  )}
                  <Close />
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-10 sm:px-9">
                  {!split && current && <h2 className="mb-5 font-serif text-[1.375rem] leading-none font-semibold">{current.label}</h2>}
                  {error && <ErrorNote text={error} className="mb-5" />}
                  {doc ? <Page page={page} doc={doc} ctx={ctx} /> : !error && <Skeleton lines={8} />}
                </div>
              </div>
            )}
          </DialogPrimitive.Content>
        </DialogPortal>
      </Dialog>
      <KeyPrompt assistant={doc?.assistant ?? null} paused={open || busy !== null || probing} probe={probe} onDoc={quickstarted} asked={asked} />
    </>
  )
}

/** 右上角的关闭；窄屏清单那一屏在标题右边 */
function Close() {
  return (
    <DialogClose asChild>
      <Button variant="ghost" size="icon-sm" className="ml-auto rounded-full" aria-label="关闭">
        <X />
      </Button>
    </DialogClose>
  )
}

/** 左栏一项：图标、名字，检查没过的项后一枚红点；开着的那项一块浅底、字加粗。窄屏每项末尾一个 › */
function NavRow({ item, active, chevron, onClick }: { item: Item; active: boolean; chevron: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-current={active ? 'page' : undefined}
            className={cn('flex w-full items-center gap-3 rounded-[10px] px-3 text-left text-[0.875rem] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ring',
                          chevron ? 'h-11' : 'h-9',
                          active ? 'bg-foreground/[0.07] font-medium text-foreground' : 'text-foreground/80 hover:bg-foreground/[0.04] hover:text-foreground')}>
      <span className={cn('flex shrink-0', active ? 'text-foreground' : 'text-muted-foreground')}>{item.icon}</span>
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      {item.bad && <span aria-label="检查没过" className="size-1.5 shrink-0 rounded-full bg-bad" />}
      {chevron && <CaretRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />}
    </button>
  )
}

function Page({ page, doc, ctx }: { page: PageId; doc: SettingsDoc; ctx: Ctx }) {
  if (page === 'literature') return <Literature doc={doc} ctx={ctx} />
  if (page === 'computes') return <Computes doc={doc} ctx={ctx} />
  if (page === 'storage') return <Storage doc={doc} ctx={ctx} />
  const entry = doc.agents.entries.find((e) => `agent:${e.name}` === page)
  if (!entry) return <General doc={doc} ctx={ctx} />
  const roles = ROLES.filter(([role]) => doc.agents[role] === entry.name).map(([, label]) => label)
  return <AgentPage key={entry.name} entry={entry} roles={roles} keys={doc.keys} ctx={ctx} />
}
