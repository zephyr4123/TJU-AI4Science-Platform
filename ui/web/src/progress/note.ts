// 悬停小签（kit.tsx 的 HoverNote）放在哪：两块面板共用。

/** 小签半宽（max-w-[16rem] 的一半）：贴边的格子，小签往里挪，不让侧滑切掉 */
const NOTE_HALF = 128

/** 悬停的那一格在面板里的位置（小签的锚点）：格子顶边的正中，左右夹在面板之内 */
export function noteAnchor(target: Element, panel: Element | null): { x: number; y: number } | null {
  if (!panel) return null
  const outer = panel.getBoundingClientRect()
  const r = target.getBoundingClientRect()
  const x = r.left + r.width / 2 - outer.left
  return { x: Math.min(Math.max(x, NOTE_HALF), Math.max(outer.width - NOTE_HALF, NOTE_HALF)), y: r.top - outer.top }
}
