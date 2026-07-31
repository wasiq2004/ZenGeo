import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { applyStoredTheme } from './components/ThemeToggle'
// Fonts before index.css so the @font-face rules land ahead of the utilities
// that reference them.
import './styles/fonts'
import './index.css'

// Applied before the first paint so the app never flashes the wrong theme.
applyStoredTheme()

const container = document.getElementById('root')
if (!container) throw new Error('Root element #root not found')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
