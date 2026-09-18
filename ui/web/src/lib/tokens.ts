// 画布类组件（ElectricBorder、ShinyText）吃的是颜色值不是 var()：从 CSS 变量里读出来，跟着深浅色变（系统切了，或页眉的开关拨了）。
import { useEffect, useState } from 'react'

import { onThemeChange } from './theme'

export function readToken(name: string): string {
  if (typeof window === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function useToken(name: string): string {
  const [value, setValue] = useState(() => readToken(name))
  useEffect(() => {
    const update = () => setValue(readToken(name))
    update()
    return onThemeChange(update)
  }, [name])
  return value
}
