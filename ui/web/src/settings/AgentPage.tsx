// 设置 → AI 下的一家（外层 #266 #268）：「状态」一节——自检（状态一行 + 检查）、版本、分工；「模型」一节——供应商、
// 它要的 key（官方登录只写终端命令，自定义填地址与模型名）、模型、思考深度。哪家、模型、深度只在这里改，对话框里没有（#257）；
// 换供应商模型回到它的起点。
import { useState } from 'react'

import { api } from '@/api/client'
import type { AgentEntry } from '@/api/types'
import CallChip from '@/components/reactbits/CallChip'
import GlideSelect from '@/components/reactbits/GlideSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

import { CHECK_MS, type Ctx, KeyField, Row, Section, StatusLine, Value } from './kit'
import { agentStatus, providerTag, shortVersion } from './status'

export function AgentPage({ entry, roles, keys, ctx }: {
  entry: AgentEntry; roles: string[]; keys: Record<string, string>; ctx: Ctx
}) {
  // 选「自定义」先不写：地址与模型名填好按「存」才一起写（没地址的自定义服务端不收）
  const [pickingCustom, setPickingCustom] = useState(false)
  const shown = pickingCustom ? 'custom' : entry.provider
  const provider = entry.providers.find((p) => p.id === shown)
  const busy = ctx.busy !== null
  const tune = (key: 'provider' | 'model' | 'effort', value: string) => {
    if (key === 'provider') setPickingCustom(value === 'custom' && entry.provider !== 'custom')
    if (key === 'provider' && value === 'custom') return
    if (value !== entry[key]) void ctx.act(`${entry.name}:${key}`, () => api.updateAgents({ agents: { [entry.name]: { [key]: value } } }))
  }
  return (
    <>
      <Section title="状态">
        <Row label="自检" note={<StatusLine status={agentStatus(entry.last_check)} />}>
          <CallChip label="检查" status={ctx.chip(`check:${entry.name}`)} expectedMs={CHECK_MS} disabled={busy}
                    onPress={() => void ctx.act(`check:${entry.name}`, () => api.runCheck('agents', entry.name),
                                                (next) => next.agents.entries.find((e) => e.name === entry.name)?.last_check?.ok === true)} />
        </Row>
        <Row label="版本"><Value>{shortVersion(entry.last_check?.version) || '未知'}</Value></Row>
        <Row label="分工"><Value className={roles.length ? '' : 'text-muted-foreground'}>{roles.join('、') || '无'}</Value></Row>
      </Section>
      <Section title="模型">
        <Row label="供应商" note={provider && providerTag(provider)}>
          <GlideSelect ariaLabel={`${entry.title} 用谁的模型`} value={shown} disabled={busy} size="md" align="right" placement="bottom"
                       options={entry.providers.map((p) => ({ value: p.id, label: p.title, tag: providerTag(p) }))}
                       onChange={(value) => tune('provider', value)} />
        </Row>
        {provider?.id === 'custom' && <CustomRows entry={entry} ctx={ctx} onSaved={() => setPickingCustom(false)} />}
        {provider?.key
          ? <Row label="key" note="只存在本机，页面只见末四位"><KeyField name={provider.key} title={provider.title} tail={keys[provider.key]} ctx={ctx} /></Row>
          : <Row label="登录" note={`在终端里运行 ai4sci agent login ${entry.name}，在浏览器里授权`} />}
        <Row label="模型">
          <GlideSelect ariaLabel={`${entry.title} 的模型`} value={entry.model} disabled={busy} size="md" align="right" placement="bottom"
                       options={entry.models.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                       onChange={(value) => tune('model', value)} />
        </Row>
        <Row label="思考深度">
          <GlideSelect ariaLabel={`${entry.title} 的思考深度`} value={entry.effort} disabled={busy} size="md" align="right" placement="bottom"
                       options={entry.efforts.map((c) => ({ value: c.id, label: c.label, tag: c.note || undefined }))}
                       onChange={(value) => tune('effort', value)} />
        </Row>
      </Section>
    </>
  )
}

/** 自定义供应商：兼容的接口地址与模型名（逗号隔开）；改完按「存」一起写 */
function CustomRows({ entry, ctx, onSaved }: { entry: AgentEntry; ctx: Ctx; onSaved: () => void }) {
  const [url, setUrl] = useState(entry.base_url)
  const [names, setNames] = useState(entry.custom_models.join(', '))
  const models = names.split(',').map((m) => m.trim()).filter(Boolean)
  const changed = entry.provider !== 'custom' || url.trim() !== entry.base_url || models.join(',') !== entry.custom_models.join(',')
  return (
    <>
      <Row label="地址" note="兼容的接口地址">
        <Input value={url} onChange={(e) => setUrl(e.target.value)} spellCheck={false} aria-label={`${entry.title} 自定义供应商的地址`}
               placeholder="https://…" className="h-8 w-[18rem] max-w-full bg-card text-[0.8125rem]" />
      </Row>
      <Row label="模型名" note="逗号隔开">
        <Input value={names} onChange={(e) => setNames(e.target.value)} spellCheck={false} aria-label={`${entry.title} 自定义供应商的模型名`}
               className="h-8 w-[14rem] max-w-full bg-card text-[0.8125rem]" />
        <Button size="sm" disabled={ctx.busy !== null || !changed || !url.trim() || models.length === 0}
                onClick={() => void ctx.act(`${entry.name}:custom`,
                                            () => api.updateAgents({ agents: { [entry.name]: { provider: 'custom', base_url: url.trim(), models } } }))
                  .then(onSaved)}>存</Button>
      </Row>
    </>
  )
}
