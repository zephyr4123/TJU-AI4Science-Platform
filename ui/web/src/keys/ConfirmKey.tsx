// 确认需求：唯一内置的门，只有人能按。按了写 requirement.lock（版本 +1）；还有「待填」按不了。
// 不要署名（主人 2026-10-05：本地部署，能按的只有你自己）：服务端记登录名。
import { useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { RequirementDetail } from '@/api/types'
import { ErrorNote } from '@/components/bits'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { useToken } from '@/lib/tokens'

import { KeyPanel } from './KeyPanel'
import { Spark } from './Spark'

export function ConfirmKey({ workspace, requirement, reload, compact = false }: {
  workspace: WorkspaceClient; requirement: RequirementDetail; reload: () => Promise<void>; compact?: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await workspace.confirm()
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const blocked = requirement.pending || !requirement.text.trim()
  const next = requirement.confirmed ? `确认 v${(requirement.version ?? 0) + 1}` : '确认需求'
  const hint = requirement.pending ? '尚有「待填」' : requirement.confirmed ? '有改动，核对后确认' : '确认后方可开工'
  return (
    <KeyPanel title={next} hint={hint} compact={compact}>
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <Spark color={amber}>
        <StarBorder glow={amber} onClick={press} disabled={busy || blocked}>{busy ? '确认中' : '确认'}</StarBorder>
      </Spark>
    </KeyPanel>
  )
}
