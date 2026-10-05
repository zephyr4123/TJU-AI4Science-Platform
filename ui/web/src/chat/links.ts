// 对话里指向本项目文件的链接（外层 #231）：助理写的是本机路径，页面直接当网址点只会落到页面外壳上。
// 认出是哪个工作区里的哪个文件，交给文件镜头打开。两种写法都认：Codex 惯写的本机绝对路径
// （…/projects/<项目>/workspaces/<工作区>/<路径>，也可能带 file://）与指南教的项目内相对路径
// （workspaces/<工作区>/<路径>）。纯函数，有单测。

export interface LocalFile {
  ws: string
  /** 工作区里的相对路径，文件镜头的 focus 就是它 */
  path: string
}

const WORKSPACE_PATH = /^workspaces\/([a-z0-9][a-z0-9-]*)\/(.+)$/

export function localFile(href: string, projectId: string): LocalFile | null {
  let path = href.replace(/^file:\/\//, '').replace(/#.*$/, '')
  if (path.startsWith('/')) {
    const marker = `/projects/${projectId}/`
    const at = path.indexOf(marker)
    if (at < 0) return null
    path = path.slice(at + marker.length)
  }
  const found = WORKSPACE_PATH.exec(path.replace(/^\.\//, ''))
  if (!found) return null
  const rest = found[2].replace(/\/+$/, '')
  return rest ? { ws: found[1], path: rest } : null
}
