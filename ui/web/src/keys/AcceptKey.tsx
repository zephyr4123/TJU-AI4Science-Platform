// 验收键：只有人能按。签的是这一版 best 与验证结论，best 再变记录就失效（后端 accept.json）。
import { useState } from 'react'

import { api } from '@/api/client'
import type { RunDetail } from '@/api/types'
import { DoneBlock, ErrorNote } from '@/components/bits'
import ClickSpark from '@/components/ClickSpark'
import { StarBorder } from '@/components/reactbits/StarBorder'
import { metric, when } from '@/lib/format'
import { useToken } from '@/lib/tokens'
import { useSigner } from '@/lib/useSigner'

import { KeyPanel } from './KeyPanel'
import { SignerField } from './SignerField'

export function AcceptKey({ run, reload }: { run: RunDetail; reload: () => Promise<void> }) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const amber = useToken('--wait')

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.accept(run.run_id, signer)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (run.accept && !run.accept.stale) {
    return (
      <DoneBlock title={`${run.accept.by} 已验收`}
                 detail={<>{when(run.accept.accepted_at)}，签的是第 {run.accept.best_iter} 轮的 {metric(run.accept.best_metric)}。</>} />
    )
  }
  const cautions: string[] = []
  if (run.accept?.stale) cautions.push(`${run.accept.by} 在 ${when(run.accept.accepted_at)} 验收过，之后结果又变了，要再看一遍。`)
  if (run.verify === null) cautions.push('还没验证。验收的会是没和结果文件对过的数字。')
  else if (run.verify.status !== 'PASS') cautions.push('验证没通过。分析里有对不上的数。')
  if (run.last_iter === 0) cautions.push('一轮都没改，只有基线，没东西可验收。')
  if (run.running || run.job) cautions.push('实验还在跑，等它停下。')
  const disabled = busy || run.running || run.job !== null || run.last_iter === 0 || !signer.trim()
  return (
    <KeyPanel title="验收这个结果"
              hint={cautions.length > 0 ? <ul className="space-y-1">{cautions.map((c) => <li key={c}>{c}</li>)}</ul>
                : '你觉得这个结果能拿去用，署名验收。这颗键只有人能按。'}>
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignerField id="accept-signer" value={signer} onChange={setSigner} />
        <ClickSpark sparkColor={amber} sparkRadius={20} sparkCount={8} duration={420}>
          <StarBorder glow={amber} onClick={press} disabled={disabled}>{busy ? '验收中…' : '验收结果'}</StarBorder>
        </ClickSpark>
      </div>
    </KeyPanel>
  )
}
