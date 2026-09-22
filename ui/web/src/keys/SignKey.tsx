// 确认一次产出：流里那一项后面有断点才需要，确认了下游才能读（signed.json）。确认之后目录又改了就 stale，要再确认。
import { useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { OutputBrief } from '@/api/types'
import { DoneBlock, ErrorNote } from '@/components/bits'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { Input } from '@/components/ui/input'
import { when } from '@/lib/format'
import { useToken } from '@/lib/tokens'
import { useSigner } from '@/lib/useSigner'

import { KeyPanel } from './KeyPanel'
import { SignerField } from './SignerField'
import { Spark } from './Spark'

export function SignKey({ workspace, output, hint, reload }: {
  workspace: WorkspaceClient; output: OutputBrief; hint: string | null; reload: () => Promise<void>
}) {
  const [signer, setSigner] = useSigner()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await workspace.sign(output.id, signer, note)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (output.signed && !output.signed.stale) {
    return <DoneBlock title={`${output.signed.by} 已确认`} detail={<>{when(output.signed.signed_at)}{output.signed.note ? ` · ${output.signed.note}` : ''}</>} />
  }
  if (output.status !== 'ok') return null
  return (
    <KeyPanel title={output.signed?.stale ? '已确认 · 之后有改动' : '确认'} hint={hint ?? '确认后，下一步方可读取'}>
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="space-y-3">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="备注（可空）" aria-label="备注" className="h-8 bg-card" />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SignerField id={`sign-${output.id}`} value={signer} onChange={setSigner} />
          <Spark color={amber}>
            <StarBorder glow={amber} onClick={press} disabled={busy || !signer.trim()}>{busy ? '确认中' : '确认'}</StarBorder>
          </Spark>
        </div>
      </div>
    </KeyPanel>
  )
}
