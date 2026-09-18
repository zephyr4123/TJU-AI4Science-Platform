// 发布键：只有人能按。签的是 manifest 与 design.md，之后改了就要重新发布（后端 publish.json）。
import { useState } from 'react'

import { api } from '@/api/client'
import type { TaskDetail } from '@/api/types'
import { DoneBlock, ErrorNote, Problems } from '@/components/bits'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { when } from '@/lib/format'
import { useToken } from '@/lib/tokens'
import { useSigner } from '@/lib/useSigner'

import { KeyPanel } from './KeyPanel'
import { SignerField } from './SignerField'
import { Spark } from './Spark'

export function PublishKey({ workspace, task, reload }: { workspace: string; task: TaskDetail; reload: () => Promise<void> }) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.publish(workspace, signer)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (task.publish.ok) {
    return (
      <DoneBlock title={`${task.publish.by} 已发布`}
                 detail={<>{when(task.publish.at)}，改了要重发</>} />
    )
  }
  const blocked = task.intake_problems.length > 0
  return (
    <KeyPanel
      title="发布需求"
      hint={task.publish.state === 'invalid' && task.publish.reason
        ? task.publish.reason
        : '署名后发布'}
    >
      {blocked && <div className="mb-3"><Problems items={task.intake_problems} tone="warn" /></div>}
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignerField id="publish-signer" value={signer} onChange={setSigner} />
        <Spark color={amber}>
          <StarBorder glow={amber} onClick={press} disabled={busy || blocked || !signer.trim()}>
            {busy ? '发布中' : '发布'}
          </StarBorder>
        </Spark>
      </div>
    </KeyPanel>
  )
}
