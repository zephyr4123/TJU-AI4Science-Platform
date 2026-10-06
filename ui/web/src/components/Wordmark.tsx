// 平台的字标（外层 #258）：无衬线粗体「AAAI4S」、字距略收，前一截墨色、「4S」靛色（与地方栏那枚标同一种靛）；悬停看全称。
// 宋体试过：拉丁字母在思源宋体里偏细偏素，像正文不像标。
// 首页左上与地方栏顶上的标连成一组门牌，窄屏的地方清单、页脚也用它。字号由用的地方给。
import { BRAND } from '@/brand'
import { cn } from '@/lib/utils'

export function Wordmark({ className }: { className?: string }) {
  return (
    <span title={BRAND.full} aria-label={BRAND.name}
          className={cn('inline-flex items-baseline font-sans leading-none font-bold tracking-[-0.015em]', className)}>
      <span aria-hidden="true">{BRAND.parts[0]}</span>
      <span aria-hidden="true" className="text-primary">{BRAND.parts[1]}</span>
    </span>
  )
}
