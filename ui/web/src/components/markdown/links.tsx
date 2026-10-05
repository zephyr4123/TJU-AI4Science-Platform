// markdown 里的链接怎么开（外层 #231）：网址新开一页（同页跳走，整个工作台的状态就没了）；本机路径交给外面给的
// open——对话里认出是本项目的文件，就在那个工作区的文件镜头里打开；认不出、或这里没人给 open，只显示文字，
// 不做成点了落到页面外壳上的死链，也不把本机目录当链接地址摆出来。
// 工作区里一份文件的正文（外层 #236）：相对链接先按这份文件所在的目录解开成项目内路径，再交给同一个 open。
import { createContext, type ReactNode, useCallback, useContext } from 'react'

/** 给一个本机路径，认得就返回「打开它」的动作，认不得返回 null */
export type OpenLink = (href: string) => (() => void) | null

export const LinkOpener = createContext<OpenLink | null>(null)

const SCHEME = /^[a-z][a-z0-9+.-]*:/i

/** 没有协议头的（绝对路径、相对路径）与 file:// 都是本机路径 */
export function isLocalPath(href: string): boolean {
  return !SCHEME.test(href) || href.startsWith('file:')
}

/** 一份 markdown 是哪个工作区里的哪份文件；对话里的不是文件，没有它 */
export interface FileAt {
  ws: string
  /** 工作区里的相对路径 */
  path: string
}

/** 文件里写的相对路径 → 项目内路径（`workspaces/<工作区>/<路径>`）；不是相对路径、只有锚点、退出了工作区的返回 null */
export function relativeTo(href: string, at: FileAt): string | null {
  const path = href.replace(/#.*$/, '')
  if (!path || SCHEME.test(path) || path.startsWith('/') || path.startsWith('workspaces/')) return null
  const parts = at.path.split('/').slice(0, -1)
  for (const part of path.split('/')) {
    if (part === '..') {
      if (!parts.length) return null
      parts.pop()
    } else if (part && part !== '.') {
      parts.push(part)
    }
  }
  return parts.length ? `workspaces/${at.ws}/${parts.join('/')}` : null
}

/** 包住一份文件的正文：相对链接按它所在的目录解开，别的原样交给外面的 open */
export function FileLinks({ at, children }: { at: FileAt; children: ReactNode }) {
  const open = useContext(LinkOpener)
  const { ws, path } = at
  const resolve = useCallback<OpenLink>((href) => open?.(relativeTo(href, { ws, path }) ?? href) ?? null, [open, ws, path])
  return <LinkOpener.Provider value={resolve}>{children}</LinkOpener.Provider>
}

export function Link({ href, children }: { href: string; children: ReactNode }) {
  const open = useContext(LinkOpener)
  if (!isLocalPath(href)) return <a href={href} target="_blank" rel="noreferrer">{children}</a>
  const action = open?.(href) ?? null
  if (!action) return <span>{children}</span>
  return <a href="#" onClick={(e) => { e.preventDefault(); action() }}>{children}</a>
}
