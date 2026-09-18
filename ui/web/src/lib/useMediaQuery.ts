// 一个媒体查询的布尔值：窄屏时脊柱收进抽屉、编辑台上下叠，靠它切。
import { useEffect, useState } from 'react'

/** 宽屏：脊柱常驻右栏、编辑台左右分栏 */
export const WIDE = '(min-width: 64rem)'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = () => setMatches(media.matches)
    onChange()
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [query])
  return matches
}
