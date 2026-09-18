// 页面里的图片与视频只在这里写 URL（纲领 P-17）：全部在自己的 CDN 上，仓里不放二进制。
// 来源、作者、许可与处理方法见 docs/DESIGN.md「素材」。CDN 缓存是 immutable：内容变了换文件名，不复用旧名。
const CDN = 'https://media.zephyrxiang.com/ai4science/v1'

/** 一段循环视频与它的首帧（减少动效、省流量、加载失败时只给首帧） */
export interface Clip { video: string; poster: string }

export const ASSETS = {
  /** 「新建工作区」那一屏的背景：浅色一段云雾，深色一段光线汇聚 */
  door: {
    light: { video: `${CDN}/video/door-light.mp4`, poster: `${CDN}/image/door-light.jpg` },
    dark: { video: `${CDN}/video/door-dark.mp4`, poster: `${CDN}/image/door-dark.jpg` },
  } satisfies Record<'light' | 'dark', Clip>,
  /** 对话欢迎屏的配图：实验室玻璃器皿，高调 */
  welcome: {
    src: `${CDN}/image/welcome-2400.jpg`,
    srcSet: `${CDN}/image/welcome-1200.jpg 1200w, ${CDN}/image/welcome-2400.jpg 2400w`,
  },
} as const

export const CDN_ORIGIN = new URL(CDN).origin
