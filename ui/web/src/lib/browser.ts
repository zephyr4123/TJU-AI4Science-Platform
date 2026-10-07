// 浏览器之间的差异，集中在这一处（外层 #282）：桌面 App 在 Mac 上是系统的 WKWebView、在 Windows 上是 WebView2，
// 页面不能再假设自己跑在 Chrome 或 Safari 的标签页里。都是纯函数，vitest 直接测。

/** WebKit 内核（Safari、iOS 上的各家浏览器、桌面 App 的 WKWebView）：UA 里有 AppleWebKit、又不是 Chromium 一族。
 *  不看 `Safari` 这个词——WKWebView 的 UA 没有它（macOS 26.5.2 实测）；Chromium 一族的 UA 里倒都写着 AppleWebKit 与 Safari。 */
export function isWebKit(ua: string): boolean {
  return /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg\//.test(ua)
}
