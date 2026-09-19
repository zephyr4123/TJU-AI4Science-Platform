// 需求确认之后助理又改了：页面把上一版确认时的原文和现在的文件按行对比，改了哪几行一眼看出来。
// 最长公共子序列的行级 diff，纯函数，够用为止（需求文档几十到几百行）。

export type DiffOp = { kind: 'same' | 'added' | 'removed'; text: string }

export function diffLines(before: string, after: string): DiffOp[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const n = a.length
  const m = b.length
  // lcs[i][j]：a[i:] 与 b[j:] 的最长公共子序列长度
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const ops: DiffOp[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) { ops.push({ kind: 'same', text: a[i] }); i++; j++ }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { ops.push({ kind: 'removed', text: a[i] }); i++ }
    else { ops.push({ kind: 'added', text: b[j] }); j++ }
  }
  while (i < n) ops.push({ kind: 'removed', text: a[i++] })
  while (j < m) ops.push({ kind: 'added', text: b[j++] })
  return ops
}

/** 改了几行：加的 + 删的 */
export function changedCount(ops: DiffOp[]): number {
  return ops.filter((op) => op.kind !== 'same').length
}
