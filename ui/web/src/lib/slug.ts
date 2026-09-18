// 文件夹名从标题里推：研究者只写一句话，名字是顺带的（外层 #79 #80）。规则要能让人猜到：拉丁字母与数字小写、连字符相连，
// 没有拉丁字符就按日期；重名往后加 -2、-3。和服务端 `workspace new` 同一口径：小写字母开头，只有小写、数字、连字符。
export const ID_RE = /^[a-z][a-z0-9-]*$/

const MAX = 40

const two = (n: number) => String(n).padStart(2, '0')

export function suggestId(title: string, taken: Iterable<string>, today: Date): string {
  // NFKD 把 ö 拆成 o + 组合符，先把组合符去掉再切词，Schrödinger 才是 schrodinger 不是 schro-dinger
  const words = title.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().match(/[a-z0-9]+/g) ?? []
  let base = words.join('-').slice(0, MAX).replace(/-+$/, '')
  if (base === '') base = `ws-${two(today.getMonth() + 1)}${two(today.getDate())}`
  else if (!/^[a-z]/.test(base)) base = `ws-${base}`
  const used = new Set(taken)
  if (!used.has(base)) return base
  for (let n = 2; ; n++) {
    const candidate = `${base}-${n}`
    if (!used.has(candidate)) return candidate
  }
}
