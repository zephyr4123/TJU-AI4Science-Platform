// 全站的图什么时候「已经在浏览器里」：页面一起来就把六张封面 + 四张底图都要一遍（预热），要到的记进 ready；
// Photo 铺图时先查 ready——在的直接就在、不在的到了再淡入。用 img 元素要而不是 fetch：srcSet / sizes 选中的那一档才是页面真会用的那张。

import { ASSETS, COVERS, type Picture } from '@/assets'

/** 这次会话里已经在浏览器里的图（按 src） */
export const ready = new Set<string>()

export function preloadPictures(): void {
  const pictures: Picture[] = [...COVERS, ASSETS.welcome, ASSETS.studio, ASSETS.chat, ASSETS.board]
  for (const picture of pictures) {
    if (ready.has(picture.src)) continue
    const img = new Image()
    img.onload = () => { ready.add(picture.src) }
    if (picture.srcSet) { img.sizes = '100vw'; img.srcset = picture.srcSet }
    img.src = picture.src
  }
}
