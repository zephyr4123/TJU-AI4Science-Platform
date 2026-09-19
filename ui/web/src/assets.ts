// 页面里的图片与视频只在这里写 URL（纲领 P-17）：全部在自己的 CDN 上，仓里不放二进制。
// 来源、作者、许可与处理方法见 docs/DESIGN.md「素材」。CDN 缓存是 immutable：内容变了换文件名，不复用旧名。
const CDN = 'https://media.zephyrxiang.com/ai4science/v1'

/** 一段循环视频与它的首帧（减少动效、省流量、加载失败时只给首帧） */
export interface Clip { video: string; poster: string }

/** 一张图：src 必有，srcSet 给宽窄两档；alt 给清单与文档看，页面上作装饰时不念 */
export interface Picture { src: string; srcSet?: string; alt: string }

/** 工作区封面：大图给抽屉与横幅，小图给顶栏与切换清单 */
export interface Cover extends Picture { key: string; thumb: string }

const cover = (key: string, alt: string): Cover => ({
  key, alt, src: `${CDN}/image/cover-${key}-800.jpg`, thumb: `${CDN}/image/cover-${key}-240.jpg`,
})

/** 六张封面：风景，按色调分开好认（主人：别用玻璃瓶、实验室味的图）；一个工作区按名字稳定地挑一张，地方栏、清单、抽屉认同一张 */
export const COVERS: readonly Cover[] = [
  cover('ridge', '雾里的山脊'),
  cover('forest', '雾中的松林'),
  cover('dunes', '晨光里的沙丘'),
  cover('sea', '黎明的海面'),
  cover('lake', '湖上的雾与倒影'),
  cover('snow', '雪原上的一棵树'),
]

/** FNV-1a 取模：同一个名字永远同一张，换台电脑也一样；六张之间撞车难免，只求散得开 */
export function coverOf(id: string): Cover {
  let h = 0x811c9dc5
  for (const ch of id) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0
  return COVERS[h % COVERS.length]
}

export const ASSETS = {
  /** 「新建工作区」那一屏的背景：浅色一段云雾，深色一段光线汇聚 */
  door: {
    light: { video: `${CDN}/video/door-light.mp4`, poster: `${CDN}/image/door-light.jpg` },
    dark: { video: `${CDN}/video/door-dark.mp4`, poster: `${CDN}/image/door-dark.jpg` },
  } satisfies Record<'light' | 'dark', Clip>,
  /** 对话欢迎屏的配图：云雾里的山，高调 */
  welcome: {
    src: `${CDN}/image/welcome-mist-2400.jpg`,
    srcSet: `${CDN}/image/welcome-mist-1200.jpg 1200w, ${CDN}/image/welcome-mist-2400.jpg 2400w`,
    alt: '云雾里的山',
  } satisfies Picture,
  /** 编辑台「库」的横幅与造流助理抽屉的封面：晨光下的山脊线 */
  studio: {
    src: `${CDN}/image/studio-dawn-2000.jpg`,
    srcSet: `${CDN}/image/studio-dawn-1000.jpg 1000w, ${CDN}/image/studio-dawn-2000.jpg 2000w`,
    alt: '晨光下的山脊线',
  } satisfies Picture,
  /** 对话正文底下的一层：淡彩的云，纱幕压到只剩氛围 */
  chat: {
    src: `${CDN}/image/chat-clouds-2400.jpg`,
    srcSet: `${CDN}/image/chat-clouds-1200.jpg 1200w, ${CDN}/image/chat-clouds-2400.jpg 2400w`,
    alt: '淡彩的云',
  } satisfies Picture,
  /** 看板底下的一层：层层山影，黑白 */
  board: {
    src: `${CDN}/image/board-ridges-1200.jpg`,
    alt: '层层的山影',
  } satisfies Picture,
} as const

export const CDN_ORIGIN = new URL(CDN).origin
