// === TASK:WP-501:START ===
import { useState } from 'react'
import type { ChatClient, CapabilityResponseEnvelope } from '../shared/ChatClient'

export interface WidgetShellProps {
  client: ChatClient
}

export function WidgetShell({ client }: WidgetShellProps) {
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState('Ready')

  async function submitMessage() {
    setStatus('Sending')
    try {
      const response: CapabilityResponseEnvelope = await client.send({
        capability: 'information_assistance',
        payload: { message },
        context: { channel: 'web_widget', locale: 'vi-VN' },
      })
      setStatus(`Received ${response.outcome}`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to send message')
    }
  }

  return (
    <section aria-label="Chat widget">
      <h2>Hospital chat widget</h2>
      <label htmlFor="widget-message">Message</label>
      <input id="widget-message" value={message} onChange={(event) => setMessage(event.target.value)} />
      <button type="button" onClick={submitMessage} disabled={message.trim().length === 0}>
        Send
      </button>
      <p role="status">{status}</p>
    </section>
  )
}
// === TASK:WP-501:END ===
