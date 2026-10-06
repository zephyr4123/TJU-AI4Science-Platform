// 设置 → 能力 → 文献检索（外层 #265 #268，纲领 P-27）：OpenAlex 的 key，可选——不填也能检索，填了额度大十倍。
import type { SettingsDoc } from '@/api/types'

import { type Ctx, KeyField, Row, Section } from './kit'

/** keys.yaml 里的名字，与 `framework/capabilities/literature_search/openalex.py` 的 KEY_NAME 同一个 */
const OPENALEX = 'openalex'

export function Literature({ doc, ctx }: { doc: SettingsDoc; ctx: Ctx }) {
  return (
    <Section title="OpenAlex">
      <Row label="key" note={<>不填也能检索，填了额度大十倍。<a href="https://openalex.org/settings/api" target="_blank" rel="noreferrer"
                                                          className="text-primary underline-offset-3 hover:underline">免费领取</a></>}>
        <KeyField name={OPENALEX} title="OpenAlex" tail={doc.keys[OPENALEX]} ctx={ctx} />
      </Row>
    </Section>
  )
}
