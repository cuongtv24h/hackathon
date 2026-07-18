// === TASK:WP-500:START ===
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /admin web/i })).toBeInTheDocument()
  })
})
// === TASK:WP-500:END ===
