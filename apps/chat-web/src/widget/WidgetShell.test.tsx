// === TASK:WP-501:START ===
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { WidgetShell } from './WidgetShell'
import type { ChatClient } from '../shared/ChatClient'
import { SSEClient } from '../shared/SSEClient'

function createClient(send: ChatClient['send']): ChatClient {
  return { send } as ChatClient
}

describe('WidgetShell', () => {
  it('sends widget context and reports a successful capability envelope', async () => {
    const send = vi.fn().mockResolvedValue({
      trace_id: 'trace-widget',
      capability: 'information_assistance',
      outcome: 'answered',
      result: { answer: 'Xin chào' },
      warnings: [],
      errors: [],
      timestamp: '2026-07-18T00:00:00.000Z',
    })

    render(<WidgetShell client={createClient(send)} />)

    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: 'Giờ khám?' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Received answered'))
    expect(send).toHaveBeenCalledWith({
      capability: 'information_assistance',
      payload: { message: 'Giờ khám?' },
      context: { channel: 'web_widget', locale: 'vi-VN' },
    })
  })

  it('keeps empty messages from being sent', () => {
    const send = vi.fn()

    render(<WidgetShell client={createClient(send)} />)

    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
    expect(send).not.toHaveBeenCalled()
  })

  it('shows client errors without network calls in the test', async () => {
    const send = vi.fn().mockRejectedValue(new Error('Capability request failed'))

    render(<WidgetShell client={createClient(send)} />)

    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: 'Help' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Capability request failed'))
  })

  it('receives named SSE completion events used by capability APIs', () => {
    const listeners: Record<string, (event: MessageEvent) => void> = {}
    const source = {
      onmessage: null,
      onerror: null,
      close: vi.fn(),
      addEventListener: vi.fn((eventName: string, listener: (event: MessageEvent) => void) => {
        listeners[eventName] = listener
      }),
    } as unknown as EventSource
    const onMessage = vi.fn()
    const client = new SSEClient({ eventSourceFactory: () => source, onMessage })

    client.connect('/v1/capabilities/information-assistance:execute')
    listeners.completed(new MessageEvent('completed', { data: '{"outcome":"answered"}' }))

    expect(onMessage).toHaveBeenCalledWith({ event: 'completed', data: { outcome: 'answered' } })
  })
})
// === TASK:WP-501:END ===
