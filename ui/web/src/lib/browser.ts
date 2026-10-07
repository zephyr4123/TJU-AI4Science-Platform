// 浏览器之间的两处差异，集中在这一处（外层 #282）：桌面 App 在 Mac 上是系统的 WKWebView、在 Windows 上是 WebView2，
// 页面不能再假设自己跑在 Chrome 或 Safari 的标签页里。都是纯函数，vitest 直接测。

/** WebKit 内核（Safari、iOS 上的各家浏览器、桌面 App 的 WKWebView）：UA 里有 AppleWebKit、又不是 Chromium 一族。
 *  不看 `Safari` 这个词——WKWebView 的 UA 没有它（macOS 26.5.2 实测）；Chromium 一族的 UA 里倒都写着 AppleWebKit 与 Safari。 */
export function isWebKit(ua: string): boolean {
  return /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg\//.test(ua)
}

/** 这次按键是不是输入法在组词：组词时的回车是选词、Esc 是撤掉候选，不是发送、新建、清空。
 *  只看 `isComposing` 不够：WebKit 用回车确认候选词的那次 keydown，isComposing 是假、keyCode 是 229
 *  （https://bugs.webkit.org/show_bug.cgi?id=165004）。调用方传 `event.nativeEvent`。 */
export function composing(event: { isComposing: boolean; keyCode: number }): boolean {
  return event.isComposing || event.keyCode === 229
}
