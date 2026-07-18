// === TASK:WP-501:START ===
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StandaloneShell } from './StandaloneShell'
import type { ChatClient } from '../shared/ChatClient'

function createClient(send: ChatClient['send']): ChatClient {
  return { send } as ChatClient
}

describe('StandaloneShell', () => {
  it('sends standalone page context and renders the answer from the envelope result', async () => {
    const send = vi.fn().mockResolvedValue({
      trace_id: 'trace-page',
      capability: 'information_assistance',
      outcome: 'answered',
      result: { answer: 'Khoa khám hoạt động từ 7:00.' },
      warnings: [],
      errors: [],
      timestamp: '2026-07-18T00:00:00.000Z',
    })

    render(<StandaloneShell client={createClient(send)} />)

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: 'Cho tôi hỏi giờ khám' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Khoa khám hoạt động từ 7:00.'))
    expect(send).toHaveBeenCalledWith({
      capability: 'information_assistance',
      payload: { message: 'Cho tôi hỏi giờ khám' },
      context: { channel: 'web_page', locale: 'vi-VN' },
    })
  })

  it('falls back to outcome when answer is absent', async () => {
    const send = vi.fn().mockResolvedValue({
      trace_id: 'trace-page',
      capability: 'information_assistance',
      outcome: 'queued',
      result: {},
      warnings: [],
      errors: [],
      timestamp: '2026-07-18T00:00:00.000Z',
    })

    render(<StandaloneShell client={createClient(send)} />)

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: 'Status' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('queued'))
  })

  it('shows client errors for failed requests', async () => {
    const send = vi.fn().mockRejectedValue(new Error('Gateway unavailable'))

    render(<StandaloneShell client={createClient(send)} />)

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: 'Help' } })
    fireEvent.click(screen.getByRole('button', { name: /ask/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Gateway unavailable'))
  })
})
// === TASK:WP-501:END ===
