// markdown 里的链接怎么开（外层 #231）：网址新开一页（同页跳走，整个工作台的状态就没了）；本机路径交给外面给的
// open——对话里认出是本项目的文件，就在那个工作区的文件镜头里打开；认不出、或这里没人给 open，只显示文字，
// 不做成点了落到页面外壳上的死链，也不把本机目录当链接地址摆出来。
import { createContext, type ReactNode, useContext } from 'react'

/** 给一个本机路径，认得就返回「打开它」的动作，认不得返回 null */
export type OpenLink = (href: string) => (() => void) | null

export const LinkOpener = createContext<OpenLink | null>(null)

/** 没有协议头的（绝对路径、相对路径）与 file:// 都是本机路径 */
export function isLocalPath(href: string): boolean {
  return !/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('file:')
}

export function Link({ href, children }: { href: string; children: ReactNode }) {
  const open = useContext(LinkOpener)
  if (!isLocalPath(href)) return <a href={href} target="_blank" rel="noreferrer">{children}</a>
  const action = open?.(href) ?? null
  if (!action) return <span>{children}</span>
  return <a href="#" onClick={(e) => { e.preventDefault(); action() }}>{children}</a>
}
