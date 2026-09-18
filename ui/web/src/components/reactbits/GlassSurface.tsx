// 一块玻璃，从 reactbits 的 GlassSurface 捞来改装（MIT，https://reactbits.dev/components/glass-surface）：
// 输入框的壳，浮在欢迎屏的配图与滚过的对话上面。改装点：深浅色跟项目的 useDark（认 data-theme）而不是只看系统；
// 尺寸缺省撑满父元素、高度随内容；去掉苹果蓝的焦点环（焦点由调用方画）；退化样式用墨色阴影不用蓝。
// 真正的折射靠 SVG 滤镜进 backdrop-filter，只有 Chromium 支持；Safari / Firefox 退化成磨砂玻璃。
import { type CSSProperties, type ReactNode, useCallback, useEffect, useId, useRef, useState } from 'react'

import { useDark } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

export interface GlassSurfaceProps {
  children?: ReactNode
  width?: number | string
  height?: number | string
  borderRadius?: number
  borderWidth?: number
  brightness?: number
  opacity?: number
  blur?: number
  displace?: number
  backgroundOpacity?: number
  saturation?: number
  distortionScale?: number
  redOffset?: number
  greenOffset?: number
  blueOffset?: number
  xChannel?: 'R' | 'G' | 'B'
  yChannel?: 'R' | 'G' | 'B'
  mixBlendMode?: CSSProperties['mixBlendMode']
  className?: string
  style?: CSSProperties
}

function supportsBackdropFilter(): boolean {
  return typeof CSS !== 'undefined' && CSS.supports('backdrop-filter', 'blur(10px)')
}

// 只有 Chromium 把 SVG 滤镜接进 backdrop-filter；WebKit 与 Firefox 会报"支持"却画不出来
function supportsSvgBackdrop(filterId: string): boolean {
  const isWebkit = /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent)
  const isFirefox = /Firefox/.test(navigator.userAgent)
  if (isWebkit || isFirefox) return false
  const div = document.createElement('div')
  div.style.backdropFilter = `url(#${filterId})`
  return div.style.backdropFilter !== ''
}

export default function GlassSurface({
  children,
  width = '100%',
  height = 'auto',
  borderRadius = 20,
  borderWidth = 0.07,
  brightness = 50,
  opacity = 0.93,
  blur = 11,
  displace = 0,
  backgroundOpacity = 0,
  saturation = 1,
  distortionScale = -180,
  redOffset = 0,
  greenOffset = 10,
  blueOffset = 20,
  xChannel = 'R',
  yChannel = 'G',
  mixBlendMode = 'difference',
  className,
  style,
}: GlassSurfaceProps) {
  const uniqueId = useId().replace(/:/g, '-')
  const filterId = `glass-filter-${uniqueId}`
  const redGradId = `red-grad-${uniqueId}`
  const blueGradId = `blue-grad-${uniqueId}`

  const [svgSupported] = useState(() => supportsSvgBackdrop(filterId))
  const containerRef = useRef<HTMLDivElement>(null)
  const feImageRef = useRef<SVGFEImageElement>(null)
  const redChannelRef = useRef<SVGFEDisplacementMapElement>(null)
  const greenChannelRef = useRef<SVGFEDisplacementMapElement>(null)
  const blueChannelRef = useRef<SVGFEDisplacementMapElement>(null)
  const gaussianBlurRef = useRef<SVGFEGaussianBlurElement>(null)
  const dark = useDark()

  const updateDisplacementMap = useCallback(() => {
    const rect = containerRef.current?.getBoundingClientRect()
    const actualWidth = rect?.width || 400
    const actualHeight = rect?.height || 200
    const edgeSize = Math.min(actualWidth, actualHeight) * (borderWidth * 0.5)
    const svgContent = `
      <svg viewBox="0 0 ${actualWidth} ${actualHeight}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="${redGradId}" x1="100%" y1="0%" x2="0%" y2="0%">
            <stop offset="0%" stop-color="#0000"/>
            <stop offset="100%" stop-color="red"/>
          </linearGradient>
          <linearGradient id="${blueGradId}" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#0000"/>
            <stop offset="100%" stop-color="blue"/>
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" fill="black"></rect>
        <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" rx="${borderRadius}" fill="url(#${redGradId})" />
        <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" rx="${borderRadius}" fill="url(#${blueGradId})" style="mix-blend-mode: ${mixBlendMode}" />
        <rect x="${edgeSize}" y="${edgeSize}" width="${actualWidth - edgeSize * 2}" height="${actualHeight - edgeSize * 2}" rx="${borderRadius}" fill="hsl(0 0% ${brightness}% / ${opacity})" style="filter:blur(${blur}px)" />
      </svg>
    `
    feImageRef.current?.setAttribute('href', `data:image/svg+xml,${encodeURIComponent(svgContent)}`)
  }, [borderRadius, borderWidth, brightness, opacity, blur, mixBlendMode, redGradId, blueGradId])

  useEffect(() => {
    updateDisplacementMap()
    for (const { ref, offset } of [
      { ref: redChannelRef, offset: redOffset },
      { ref: greenChannelRef, offset: greenOffset },
      { ref: blueChannelRef, offset: blueOffset },
    ]) {
      if (ref.current) {
        ref.current.setAttribute('scale', (distortionScale + offset).toString())
        ref.current.setAttribute('xChannelSelector', xChannel)
        ref.current.setAttribute('yChannelSelector', yChannel)
      }
    }
    gaussianBlurRef.current?.setAttribute('stdDeviation', displace.toString())
  }, [updateDisplacementMap, displace, distortionScale, redOffset, greenOffset, blueOffset, xChannel, yChannel])

  useEffect(() => {
    if (!containerRef.current) return
    // 高度随内容长，位移图要跟着重画
    const observer = new ResizeObserver(() => { setTimeout(updateDisplacementMap, 0) })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [updateDisplacementMap])

  useEffect(() => { setTimeout(updateDisplacementMap, 0) }, [updateDisplacementMap, width, height])

  const base: CSSProperties = {
    ...style,
    width: typeof width === 'number' ? `${width}px` : width,
    height: typeof height === 'number' ? `${height}px` : height,
    borderRadius: `${borderRadius}px`,
  }
  const inkShadow = `0px 4px 16px rgba(17, 17, 26, 0.05), 0px 8px 24px rgba(17, 17, 26, 0.05), 0px 16px 56px rgba(17, 17, 26, 0.05)`
  const surface: CSSProperties = svgSupported
    ? {
      ...base,
      background: dark ? `hsl(0 0% 0% / ${backgroundOpacity})` : `hsl(0 0% 100% / ${backgroundOpacity})`,
      backdropFilter: `url(#${filterId}) saturate(${saturation})`,
      boxShadow: dark
        ? `0 0 2px 1px color-mix(in oklch, white, transparent 65%) inset, 0 0 10px 4px color-mix(in oklch, white, transparent 85%) inset, ${inkShadow}`
        : `0 0 2px 1px color-mix(in oklch, black, transparent 85%) inset, 0 0 10px 4px color-mix(in oklch, black, transparent 90%) inset, ${inkShadow}`,
    }
    : supportsBackdropFilter()
      ? {
        ...base,
        background: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.35)',
        backdropFilter: 'blur(12px) saturate(1.6)',
        WebkitBackdropFilter: 'blur(12px) saturate(1.6)',
        border: `1px solid ${dark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(255, 255, 255, 0.5)'}`,
        boxShadow: `${inkShadow}, inset 0 1px 0 0 rgba(255, 255, 255, ${dark ? 0.2 : 0.5})`,
      }
      : {
        ...base,
        background: dark ? 'rgba(0, 0, 0, 0.4)' : 'rgba(255, 255, 255, 0.6)',
        border: `1px solid ${dark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.4)'}`,
        boxShadow: inkShadow,
      }

  return (
    <div ref={containerRef} className={cn('relative overflow-hidden transition-opacity duration-[260ms] ease-out', className)} style={surface}>
      <svg className="pointer-events-none absolute inset-0 -z-10 h-full w-full opacity-0" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id={filterId} colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
            <feImage ref={feImageRef} x="0" y="0" width="100%" height="100%" preserveAspectRatio="none" result="map" />
            <feDisplacementMap ref={redChannelRef} in="SourceGraphic" in2="map" result="dispRed" />
            <feColorMatrix in="dispRed" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="red" />
            <feDisplacementMap ref={greenChannelRef} in="SourceGraphic" in2="map" result="dispGreen" />
            <feColorMatrix in="dispGreen" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="green" />
            <feDisplacementMap ref={blueChannelRef} in="SourceGraphic" in2="map" result="dispBlue" />
            <feColorMatrix in="dispBlue" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="blue" />
            <feBlend in="red" in2="green" mode="screen" result="rg" />
            <feBlend in="rg" in2="blue" mode="screen" result="output" />
            <feGaussianBlur ref={gaussianBlurRef} in="output" stdDeviation="0.7" />
          </filter>
        </defs>
      </svg>
      <div className="relative z-10 h-full w-full rounded-[inherit]">{children}</div>
    </div>
  )
}
