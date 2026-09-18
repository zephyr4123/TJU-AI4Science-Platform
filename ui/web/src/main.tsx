import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import './index.css'
import { applyTheme, storedTheme } from './lib/theme'

// 本机记过深浅色就先写到 <html> 上再画，不闪一下
applyTheme(storedTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
