// 设置 → 平台 → 存放（外层 #263 #268）：「平台的家」在哪、几个项目与工作区、剩多少空间；「占用」家里每块多大——
// 要走遍整棵树、一秒上下，所以这页打开时单独取（`GET /settings/storage`），取回之前每行写「计算中」；
// 「清除」一行，按住才算数——平台建的家才有这一节（AI4SCI_HOME 指到别处的不认）。
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import type { SettingsDoc, StoragePart } from '@/api/types'
import HoldButton from '@/components/reactbits/HoldButton'
import { bytes } from '@/lib/format'

import { type Ctx, Row, Section, Value } from './kit'
import { tildify } from './status'

/** 「占用」的几块，与 `framework/chat/settings.py` 的 PARTS 同序；取回之前先按这几行摆着 */
const PART_LABELS = ['项目', '编辑台', '会话与登录', '依赖缓存', '设置与 key']

export function Storage({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  const s = doc.storage
  const [parts, setParts] = useState<StoragePart[] | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  // 整份换了（清除、改了别的）就重算一遍
  useEffect(() => {
    api.storageSizes().then((got) => { setParts(got.parts); setFailed(null) })
      .catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }, [doc])
  const rows = parts ?? PART_LABELS.map((label) => ({ label, bytes: null }))
  return (
    <>
      <Section title="平台的家">
        <Row label="位置" note={s.writable ? undefined : <span className="text-bad">不可写</span>}>
          <Value title={s.home}>{tildify(s.home)}</Value>
        </Row>
        <Row label="项目"><Value>{s.projects} 个</Value></Row>
        <Row label="工作区"><Value>{s.workspaces} 个</Value></Row>
        <Row label="剩余空间"><Value>{Math.round(s.free_gb)} GB</Value></Row>
      </Section>
      <Section title="占用">
        {rows.map((part) => (
          <Row key={part.label} label={part.label}>
            {part.bytes !== null
              ? <Value>{bytes(part.bytes)}</Value>
              : failed
                ? <Value className="text-bad" title={failed}>未取到</Value>
                : <Value className="text-muted-foreground">计算中</Value>}
          </Row>
        ))}
      </Section>
      {s.resettable && (
        <Section title="清除">
          <Row label="清除全部数据" note="登出两家、删掉以上全部，回到刚装好的样子">
            <HoldButton disabled={ctx.busy !== null} onHold={() => void ctx.act('reset', () => api.resetHome())} doneLabel="已清除">清除</HoldButton>
          </Row>
        </Section>
      )}
    </>
  )
}
