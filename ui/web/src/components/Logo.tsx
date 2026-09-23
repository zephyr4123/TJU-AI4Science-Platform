// 平台的标（外层 #139）：一只实心锥形瓶，瓶里一枚四角星芒与液面镂空——瓶是科学，星芒是 AI。主人 2026-09-23 用 ChatGPT Image
// 出的四格里选的右下角，按原图描成一条 evenodd 路径（64 × 64，瓶高 60、宽 54，居中）。内联 SVG、currentColor：地方栏的玻璃标记里
// 是白的，对话入口里是靛（深色模式跟 --primary）。public/favicon.svg 是同一条路径，components/logo.test.ts 对账。
export const LOGO_PATH =
  'M22.3 2H41.7A3.2 3.2 0 0 1 44.9 5.2V5.8A3.2 3.2 0 0 1 41.7 9Q41 9 41 10.2V17.5Q41 19.7 42 21.7L58.45 53.2A6 6 0 0 1 53.1 62H10.9A6 6 0 0 1 5.55 53.2L22 21.7Q23 19.7 23 17.5V10.2Q23 9 22.3 9A3.2 3.2 0 0 1 19.1 5.8V5.2A3.2 3.2 0 0 1 22.3 2ZM32 23.3Q34.3 29.6 40.2 31.9Q34.3 34.2 32 40.5Q29.7 34.2 23.8 31.9Q29.7 29.6 32 23.3ZM14.5 43.8C16 42.4 18.7 41.8 20.7 41.8C27 41.8 31 47.4 38.5 47.4C43 47.4 45.5 45 48.3 45C49.6 45 50.9 46.4 51.7 48.1L55.26 54.93A2.5 2.5 0 0 1 53.04 58.6H10.96A2.5 2.5 0 0 1 8.74 54.93Z'

/** 平台的标；给了 label 才是一枚图（role=img），不给就是装饰 */
export function Logo({ className, label }: { className?: string; label?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="currentColor" fillRule="evenodd"
         role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <path d={LOGO_PATH} />
    </svg>
  )
}
