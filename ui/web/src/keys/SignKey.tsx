// 确认一次产出：流里那一项后面有断点才需要，确认了下游才能读（signed.json）。确认之后目录又改了就 stale，要再确认。
// 只有一颗键（主人 2026-10-05：本地部署，能按的只有你自己——不要署名、不要备注、不要说明框）；确认了没有、何时确认，
// 写在记录「状态」那一行。
import { useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { OutputBrief } from '@/api/types'
import { ErrorNote } from '@/components/bits'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { useToken } from '@/lib/tokens'

import { Spark } from './Spark'

export function SignKey({ workspace, output, reload }: {
  workspace: WorkspaceClient; output: OutputBrief; reload: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await workspace.sign(output.id)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (output.status !== 'ok' || (output.signed && !output.signed.stale)) return null
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Spark color={amber}>
        <StarBorder glow={amber} onClick={press} disabled={busy}>{busy ? '确认中' : output.signed ? '重新确认' : '确认'}</StarBorder>
      </Spark>
      {error && <ErrorNote text={error} />}
    </div>
  )
}
