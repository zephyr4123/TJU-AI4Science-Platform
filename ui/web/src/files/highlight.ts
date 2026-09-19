// 代码高亮：highlight.js 只装五种语言（课题里会出现的：python / yaml / json / shell / ini），按后缀选；
// 不认识的后缀原样。配色在 index.css 的 `.hl` 里，只用站内的几个色：关键字靛、字符串铜绿、数字琥珀、注释灰。
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import ini from 'highlight.js/lib/languages/ini'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import yaml from 'highlight.js/lib/languages/yaml'

hljs.registerLanguage('python', python)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('ini', ini)

const BY_SUFFIX: Record<string, string> = {
  py: 'python', yaml: 'yaml', yml: 'yaml', json: 'json', sh: 'bash', bash: 'bash', toml: 'ini', ini: 'ini', cfg: 'ini',
}

/** 文件名 → 语言名；不认识就 null（原样显示） */
export function languageOf(path: string): string | null {
  const suffix = path.split('.').pop()?.toLowerCase() ?? ''
  return BY_SUFFIX[suffix] ?? null
}

/** 整段高亮成 HTML（hljs 自己转义）；没有语言就只转义 */
export function highlight(text: string, language: string | null): string {
  if (language === null) return escape(text)
  return hljs.highlight(text, { language, ignoreIllegals: true }).value
}

function escape(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
