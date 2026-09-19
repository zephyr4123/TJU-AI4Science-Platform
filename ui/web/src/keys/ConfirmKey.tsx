// 确认需求：唯一内置的门，只有人能按。按了写 requirement.lock（版本 +1）；还有「待填」按不了。
import { useState } from 'react'

import { api } from '@/api/client'
import type { RequirementDetail } from '@/api/types'
import { ErrorNote } from '@/components/bits'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { useToken } from '@/lib/tokens'
import { useSigner } from '@/lib/useSigner'

import { KeyPanel } from './KeyPanel'
import { SignerField } from './SignerField'
import { Spark } from './Spark'

export function ConfirmKey({ workspace, requirement, reload, compact = false }: {
  workspace: string; requirement: RequirementDetail; reload: () => Promise<void>; compact?: boolean
}) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.confirm(workspace, signer)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const blocked = requirement.pending || !requirement.text.trim()
  const next = requirement.confirmed ? `确认 v${(requirement.version ?? 0) + 1}` : '确认需求'
  const hint = requirement.pending ? '还有「待填」' : requirement.confirmed ? '改过了，看过 diff 再确认' : '署名后确认，阶段才能开工'
  return (
    <KeyPanel title={next} hint={hint} compact={compact}>
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignerField id="confirm-signer" value={signer} onChange={setSigner} />
        <Spark color={amber}>
          <StarBorder glow={amber} onClick={press} disabled={busy || blocked || !signer.trim()}>
            {busy ? '确认中' : '确认'}
          </StarBorder>
        </Spark>
      </div>
    </KeyPanel>
  )
}
