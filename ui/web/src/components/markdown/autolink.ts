// GFM 的自动链接只认 ASCII 标点当结尾，中文标点（`）。，；` 之类）会被一并吞进网址：
// 「https://arxiv.org/abs/2609.01558）。」整个成了链接，点开 404。这一层把结尾的中文标点从链接里挪出来。

import type { Root } from 'mdast'

/** 链接结尾不该属于网址的那些字符：全角标点、中文书名号引号、省略号 */
const TRAILING = /[　-〿！-／：-＠［-｀｛-･‘’“”…]+$/u

/** 把网址结尾的中文标点切下来：`{ url, tail }`，没有就 tail 为空串 */
export function splitTrailingPunct(url: string): { url: string; tail: string } {
  const match = TRAILING.exec(url)
  if (!match) return { url, tail: '' }
  return { url: url.slice(0, match.index), tail: match[0] }
}

/** 自动链接（文字与网址一样的 link 节点）结尾的中文标点挪到链接外面。remark 插件，原地改树。 */
export function remarkTrimAutolink() {
  return (tree: Root) => { visit(tree as unknown as AnyNode) }
}

/** 只看树的形状，不套 mdast 那一整套联合类型：有 children 就往下走，是自动链接就改 */
interface AnyNode { type: string; children?: AnyNode[]; url?: string; value?: string }

function visit(node: AnyNode): void {
  if (!node.children) return
  for (let i = 0; i < node.children.length; i += 1) {
    const child = node.children[i]
    if (child.type === 'link' && isAutolink(child)) {
      const { url, tail } = splitTrailingPunct(child.url ?? '')
      if (tail && child.children) {
        child.url = url
        child.children[0].value = url
        node.children.splice(i + 1, 0, { type: 'text', value: tail })
        i += 1
      }
      continue
    }
    visit(child)
  }
}

function isAutolink(link: AnyNode): boolean {
  return link.children?.length === 1 && link.children[0].type === 'text' && link.children[0].value === link.url
}
