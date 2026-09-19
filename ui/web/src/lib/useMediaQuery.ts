// 一个媒体查询的布尔值：窄屏时对话收进抽屉、编辑台上下叠，靠它切。
import { useEffect, useState, useSyncExternalStore } from 'react'

import { isDark, onThemeChange } from './theme'

/** 宽屏：对话常驻右栏、编辑台左右分栏 */
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

/** 深色与否：系统偏好，或页眉的开关拨的那个（`lib/theme.ts`）；拨了这里跟着变 */
export function useDark(): boolean {
  return useSyncExternalStore(onThemeChange, isDark)
}
