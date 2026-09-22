// 深浅色（外层 #91 #134）：没选过就跟系统；设置 → 外观里选了就记在本机（localStorage），写到 `<html data-theme>`——
// index.css 的规则与 useDark 都认这个属性。改了广播一个 `themechange`，读 tokens 的画布组件（ShinyText 之类）据此重读颜色。
import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

/** 系统的深色偏好；`<html data-theme>` 可压过它——与 index.css 里的规则同一口径 */
export const DARK = '(prefers-color-scheme: dark)'

const KEY = 'theme'
export const THEME_EVENT = 'themechange'

/** 本机记的选；没选过、或浏览器不让读（隐私窗口）就是 null */
export function storedTheme(): Theme | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw === 'light' || raw === 'dark' ? raw : null
  } catch {
    return null  // 读不到就当没选过：跟系统
  }
}

/** 写到 <html> 上并广播；null 是回到跟系统 */
export function applyTheme(theme: Theme | null): void {
  const root = document.documentElement
  if (theme) root.dataset.theme = theme
  else delete root.dataset.theme
  root.style.colorScheme = theme ?? ''
  window.dispatchEvent(new Event(THEME_EVENT))
}

/** 此刻是不是深色：<html data-theme> 优先，其次系统 */
export function isDark(): boolean {
  const forced = document.documentElement.dataset.theme
  return forced === 'dark' || (forced !== 'light' && window.matchMedia(DARK).matches)
}

/** 深浅色一变（开关按了，或系统切了）就叫一下 */
export function onThemeChange(callback: () => void): () => void {
  const media = window.matchMedia(DARK)
  media.addEventListener('change', callback)
  window.addEventListener(THEME_EVENT, callback)
  return () => {
    media.removeEventListener('change', callback)
    window.removeEventListener(THEME_EVENT, callback)
  }
}

/** 设置 → 外观的三档：浅、深、跟随系统（没记过就是跟随系统） */
export type ThemeChoice = Theme | 'system'

export function themeChoice(): ThemeChoice {
  return storedTheme() ?? 'system'
}

/** 设置 → 外观用：此刻选的是哪档，以及换一档（跟随系统 = 清掉记的，交回给系统） */
export function useThemeChoice(): { choice: ThemeChoice; setChoice: (next: ThemeChoice) => void } {
  const choice = useSyncExternalStore(onThemeChange, themeChoice)
  const setChoice = useCallback((next: ThemeChoice) => {
    try {
      if (next === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, next)
    } catch {
      // 记不住（隐私窗口）也照样切，只是下次打开跟系统
    }
    applyTheme(next === 'system' ? null : next)
  }, [])
  return { choice, setChoice }
}
