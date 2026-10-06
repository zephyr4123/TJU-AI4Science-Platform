// 平台在页面上叫什么（外层 #258，主人 2026-10-06：项目改名了，照公众号第一篇文章同步前端的名字，后端的名字照旧）：
// 名字、全称与口号都取自 docs/articles/2026-0929-first-release/。只在这里写一次；index.html 的 <title> 不能 import，
// 由 brand.test.ts 对账。`ai4sci` 命令、包名、仓库名不改。
export const BRAND = {
  name: 'AAAI4S',
  /** 名字里前后两截：字标上前一截是墨色、后一截是靛色 */
  parts: ['AAAI', '4S'],
  full: 'Automated Alignment AI4S',
  motto: '可编排、可追溯的自动化科研',
} as const
