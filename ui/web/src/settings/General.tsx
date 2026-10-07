// 设置 → 常规（外层 #268）：「分工」两行橡皮滑块选助理、执行层各用哪家（改了只对之后开的对话生效，P-25），
// 助理那家缺 key、说不了话时那一行底下一句红字写原因（外层 #282：余额不足、连不上不弹窗，只在这里说；缺 key 的旁边一个
// 「填 key」，跳过了那扇窗的人从这里回去）；
// 「自检」一行检查全部；「外观」一行选深浅色（记在本机，`lib/theme.ts`）。
import { Desktop, Moon, Sun } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import { api } from '@/api/client'
import type { AgentEntry, SettingsDoc } from '@/api/types'
import { BrandIcon } from '@/components/BrandIcon'
import CallChip from '@/components/reactbits/CallChip'
import RubberSegment from '@/components/reactbits/RubberSegment'
import { type ThemeChoice, useThemeChoice } from '@/lib/theme'

import { type Ctx, Row, Section } from './kit'
import { assistantNote, noWebNote, ROLES } from './status'

const CHECK_ALL_MS = 16000
const THEMES: { value: ThemeChoice; label: string; icon: ReactNode }[] = [
  { value: 'system', label: '自动', icon: <Desktop className="size-4" /> },
  { value: 'light', label: '浅色', icon: <Sun className="size-4" /> },
  { value: 'dark', label: '深色', icon: <Moon className="size-4" /> },
]

export function General({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  const table = doc.agents
  const items = table.entries.map((e) => ({ value: e.name, label: e.title, icon: <BrandIcon name={e.name} className="size-3.5" /> }))
  const { choice, setChoice } = useThemeChoice()
  return (
    <>
      <Section title="分工" note="只对之后开的对话生效">
        {ROLES.map(([role, label, note]) => (
          <Row key={role} label={label}
               note={<>{note}<RoleWarning entry={table.entries.find((e) => e.name === table[role])}
                                          problem={role === 'chat' ? assistantNote(doc.assistant) : undefined}
                                          onAsk={role === 'chat' && doc.assistant.state === 'needs_key' ? ctx.askKey : undefined} /></>}>
            <RubberSegment aria-label={`${label}用哪家`} items={items} value={table[role]} size="md" radius={14} equalSlots={false}
                           disabled={ctx.busy !== null}
                           onChange={(name) => { if (name !== table[role]) void ctx.act(role, () => api.updateAgents({ [role]: name })) }} />
          </Row>
        ))}
      </Section>
      <Section title="自检">
        <Row label="AI 与算力" note={checkedAt(doc)}>
          <CallChip label="检查全部" status={ctx.chip('all')} expectedMs={CHECK_ALL_MS} disabled={ctx.busy !== null}
                    onPress={() => void ctx.act('all', () => api.runCheck('all'), allOk)} />
        </Row>
      </Section>
      <Section title="外观">
        <Row label="主题">
          <RubberSegment aria-label="主题" items={THEMES} value={choice} size="md" radius={14} equalSlots={false}
                         onChange={(value) => setChoice(value as ThemeChoice)} />
        </Row>
      </Section>
    </>
  )
}

/** 这一层用的那家接的供应商不能联网：琥珀色一行，只提醒不拦（外层 #266）；助理此刻说不了话：红字一行写原因（外层 #282） */
function RoleWarning({ entry, problem, onAsk }: { entry?: AgentEntry; problem?: string; onAsk?: () => void }) {
  const warning = entry && noWebNote(entry)
  return (
    <>
      {warning && <span className="mt-0.5 block text-wait">{warning}</span>}
      {problem && (
        <span className="mt-0.5 block text-bad">
          {problem}
          {onAsk && <button type="button" onClick={onAsk} className="ml-2 cursor-pointer text-primary underline-offset-3 hover:underline">填 key</button>}
        </span>
      )}
    </>
  )
}

/** 全部检查算不算过：每家底座与每台算力上次检查都过了（本机不落盘、没记就算过） */
const allOk = (doc: SettingsDoc) =>
  doc.agents.entries.every((e) => e.last_check?.ok !== false) && doc.computes.every((c) => c.last_check?.ok !== false)

function checkedAt(doc: SettingsDoc): string {
  const stamps = doc.agents.entries.map((e) => e.last_check?.at).filter((s): s is string => !!s)
  if (!stamps.length) return '未检查'
  const latest = stamps.sort().at(-1)!
  return `上次检查 ${new Date(latest).toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
}
