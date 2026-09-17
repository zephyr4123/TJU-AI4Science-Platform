// 画布类组件（ElectricBorder、ShinyText）吃的是颜色值不是 var()：从 CSS 变量里读出来，跟着深浅色变。
import { useEffect, useState } from 'react'

export function readToken(name: string): string {
  if (typeof window === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function useToken(name: string): string {
  const [value, setValue] = useState(() => readToken(name))
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setValue(readToken(name))
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [name])
  return value
}
