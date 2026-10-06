// 设置 → 平台 → 算力（外层 #134 #268，纲领 P-23）：「机器」一节，一台一行——名字（缺省那台带一枚小签）、状态与地址、
// 没过时机器的原话；检查与移除靠右。节头「添加」点了才在清单末尾展开一格：贴一行 ssh、密钥路径、名字从主机名推，加完收回去。
import { ArrowsClockwise, Plus } from '@phosphor-icons/react'
import { useState } from 'react'

import { api } from '@/api/client'
import type { ComputeRow, SettingsDoc } from '@/api/types'
import CallChip from '@/components/reactbits/CallChip'
import HoldButton from '@/components/reactbits/HoldButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import { CHECK_MS, type Ctx, Row, Section, StatusLine } from './kit'
import { computeStatus, parseSsh, suggestComputeName } from './status'

export function Computes({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  const [adding, setAdding] = useState(false)
  return (
    <Section title="机器" note={`${doc.computes.length} 台`}
             action={!adding && (
               <Button variant="outline" size="sm" className="rounded-full bg-card/70" disabled={ctx.busy !== null} onClick={() => setAdding(true)}>
                 <Plus weight="bold" data-icon="inline-start" />添加
               </Button>
             )}>
      {doc.computes.map((row) => <Machine key={row.name} row={row} ctx={ctx} />)}
      {adding && <AddCompute ctx={ctx} onDone={() => setAdding(false)} />}
    </Section>
  )
}

function Machine({ row, ctx }: { row: ComputeRow; ctx: Ctx }) {
  const label = (
    <span className="flex items-baseline gap-2">
      {row.name}
      {row.default && <span className="rounded-full bg-foreground/[0.06] px-1.5 py-px text-[0.6875rem] font-normal text-muted-foreground">缺省</span>}
    </span>
  )
  return (
    <Row label={label} note={<StatusLine status={computeStatus(row.last_check)} tail={row.where} />}>
      <CallChip label="检查" status={ctx.chip(`compute:${row.name}`)} expectedMs={CHECK_MS} disabled={ctx.busy !== null}
                onPress={() => void ctx.act(`compute:${row.name}`, () => api.runCheck('computes', row.name),
                                            (next) => next.computes.find((c) => c.name === row.name)?.last_check?.ok !== false)} />
      {row.kind !== 'local' && (
        <HoldButton disabled={ctx.busy !== null} onHold={() => void ctx.act(`remove:${row.name}`, () => api.removeCompute(row.name))}>
          移除
        </HoldButton>
      )}
    </Row>
  )
}

/** 贴一行 ssh、密钥路径、名字；加完收回去 */
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
    <div className="space-y-3 py-4">
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
