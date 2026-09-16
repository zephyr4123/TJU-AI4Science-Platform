import { useEffect, useState } from 'react'

const KEY = 'ai4sci.signer'

/** 两颗键都要署名；名字记在浏览器里，下次不用再填。 */
export function useSigner(): [string, (value: string) => void] {
  const [signer, setSigner] = useState(() => {
    try {
      return window.localStorage.getItem(KEY) ?? ''
    } catch {
      return ''
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(KEY, signer)
    } catch {
      // 隐私模式下存不了就每次填，功能不受影响
    }
  }, [signer])
  return [signer, setSigner]
}
