// 页面里的图片与视频只在这里写 URL（纲领 P-17）：全部在自己的 CDN 上，仓里不放二进制。
// 来源、作者、许可与处理方法见 docs/DESIGN.md「素材」。CDN 缓存是 immutable：内容变了换文件名，不复用旧名。
const CDN = 'https://media.zephyrxiang.com/ai4science/v1'

/** 一段循环视频与它的首帧（减少动效、省流量、加载失败时只给首帧） */
export interface Clip { video: string; poster: string }

/** 一张图：src 必有，srcSet 给宽窄两档；alt 给清单与文档看，页面上作装饰时不念 */
export interface Picture { src: string; srcSet?: string; alt: string }

export const ASSETS = {
  /** 门口那一屏（起项目）的背景：浅色一段云雾，深色一段光线汇聚 */
  door: {
    light: { video: `${CDN}/video/door-light.mp4`, poster: `${CDN}/image/door-light.jpg` },
    dark: { video: `${CDN}/video/door-dark.mp4`, poster: `${CDN}/image/door-dark.jpg` },
  } satisfies Record<'light' | 'dark', Clip>,
  /** 全站唯一的底图：云雾里的山，高调冷灰（外层 #251，主人 2026-10-06：别的页面有偏黄的沙漠、橙色的晨光，色调不一，
   *  统一成首页这一张）。首页、项目页、对话、工作区看板、设置、编辑台的大背景，页眉与对话抽屉顶上那条都是它 */
  backdrop: {
    src: `${CDN}/image/welcome-mist-2400.jpg`,
    srcSet: `${CDN}/image/welcome-mist-1200.jpg 1200w, ${CDN}/image/welcome-mist-2400.jpg 2400w`,
    alt: '云雾里的山',
  } satisfies Picture,
} as const

export const CDN_ORIGIN = new URL(CDN).origin
