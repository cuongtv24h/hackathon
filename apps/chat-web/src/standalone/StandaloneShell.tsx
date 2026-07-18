// === TASK:WP-501:START ===
import { useState } from 'react'
import { SpeechInput, type SpeechRecognitionProvider } from '../features/speech-to-text'
import type { ChatClient, CapabilityResponseEnvelope } from '../shared/ChatClient'

export interface StandaloneShellProps {
  client: ChatClient
  speechRecognitionProvider?: SpeechRecognitionProvider
}

export function StandaloneShell({ client, speechRecognitionProvider }: StandaloneShellProps) {
  const [prompt, setPrompt] = useState('')
  const [reply, setReply] = useState('Standalone channel ready')

  async function ask() {
    setReply('Sending')
    try {
      const response: CapabilityResponseEnvelope<{ answer?: string }> = await client.send({
        capability: 'information_assistance',
        payload: { message: prompt },
        context: { channel: 'web_page', locale: 'vi-VN' },
      })
      setReply(response.result.answer ?? response.outcome)
    } catch (error) {
      setReply(error instanceof Error ? error.message : 'Unable to send prompt')
    }
  }

  return (
    <main aria-label="Standalone chat">
      <h1>Hospital chat</h1>
      <label htmlFor="standalone-prompt">Prompt</label>
      <textarea id="standalone-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      <SpeechInput value={prompt} onChange={setPrompt} provider={speechRecognitionProvider} />
      <button type="button" onClick={ask} disabled={prompt.trim().length === 0}>
        Ask
      </button>
      <p role="status">{reply}</p>
    </main>
  )
}
// === TASK:WP-501:END ===
