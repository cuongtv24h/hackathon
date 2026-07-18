// === TASK:WP-501:START ===
export type ChatCapability =
  | 'information_assistance'
  | 'emergency_safety'
  | 'appointment_booking'
  | 'appointment_status'

export type ClientChannel = 'web_widget' | 'web_page'

export interface ClientContextDTO {
  channel: ClientChannel
  locale: 'vi-VN'
  timezone?: string
}

export interface ChannelConfigurationDTO {
  channel_id: string
  type: 'website' | 'zalo' | 'hotline' | 'counter' | 'emergency'
  label: string
  target: string
  operating_hours?: string
  is_active: boolean
  effective_date: string
}

export interface CapabilityErrorDTO {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface CapabilityResponseEnvelope<TResult = unknown> {
  trace_id: string
  capability: ChatCapability
  outcome: string
  result: TResult
  explainability?: unknown
  warnings: string[]
  errors: CapabilityErrorDTO[]
  timestamp: string
}

export interface ChatClientRequest<TPayload = Record<string, unknown>> {
  capability: ChatCapability
  payload: TPayload
  context: ClientContextDTO
  idempotencyKey?: string
}

export interface ChatClientOptions {
  baseUrl: string
  fetcher?: typeof fetch
  defaultContext?: ClientContextDTO
}

export class ChatClientError extends Error {
  readonly status: number
  readonly envelope?: CapabilityResponseEnvelope

  constructor(message: string, status: number, envelope?: CapabilityResponseEnvelope) {
    super(message)
    this.name = 'ChatClientError'
    this.status = status
    this.envelope = envelope
  }
}

const capabilityPath: Record<ChatCapability, string> = {
  information_assistance: '/v1/capabilities/information-assistance:execute',
  emergency_safety: '/v1/capabilities/emergency-safety:execute',
  appointment_booking: '/v1/capabilities/appointment-booking:execute',
  appointment_status: '/v1/capabilities/appointment-status:execute',
}

export interface FoundationPage<TItem> {
  items: TItem[]
  total: number
  page: number
  page_size: number
}

const defaultClientContext: ClientContextDTO = {
  channel: 'web_page',
  locale: 'vi-VN',
}

export class ChatClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch
  private readonly defaultContext: ClientContextDTO

  constructor(options: ChatClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '')
    // Window.fetch requires its original receiver in real browsers.  Keep an
    // injected test fetcher unchanged, but bind the browser implementation.
    this.fetcher = options.fetcher ?? fetch.bind(globalThis)
    this.defaultContext = options.defaultContext ?? defaultClientContext
  }

  async send<TPayload extends Record<string, unknown>, TResult = unknown>(
    request: ChatClientRequest<TPayload>,
  ): Promise<CapabilityResponseEnvelope<TResult>> {
    const response = await this.fetcher(`${this.baseUrl}${capabilityPath[request.capability]}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(request.idempotencyKey ? { 'Idempotency-Key': request.idempotencyKey } : {}),
      },
      body: JSON.stringify({
        ...request.payload,
        client_context: {
          ...this.defaultContext,
          ...request.context,
        },
      }),
    })

    const body = (await response.json()) as CapabilityResponseEnvelope<TResult>

    if (!response.ok || body.errors.length > 0) {
      throw new ChatClientError(body.errors[0]?.message ?? 'Capability request failed', response.status, body)
    }

    return body
  }

  async get<TResult>(path: string): Promise<TResult> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      headers: { Accept: 'application/json' },
    })
    const body = await response.json().catch(() => undefined) as TResult | CapabilityResponseEnvelope | undefined

    if (!response.ok) {
      const envelope = body as CapabilityResponseEnvelope | undefined
      throw new ChatClientError(envelope?.errors?.[0]?.message ?? 'Foundation request failed', response.status, envelope)
    }

    return body as TResult
  }

  async sendStream<TPayload extends Record<string, unknown>, TResult = unknown>(
    request: ChatClientRequest<TPayload>,
    onEvent: (event: string, envelope: CapabilityResponseEnvelope<TResult>) => void,
  ): Promise<void> {
    const response = await this.fetcher(`${this.baseUrl}${capabilityPath[request.capability]}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        ...request.payload,
        response_mode: 'stream',
        client_context: { ...this.defaultContext, ...request.context },
      }),
    })
    if (!response.ok || !response.body) {
      const body = (await response.json().catch(() => undefined)) as CapabilityResponseEnvelope | undefined
      throw new ChatClientError(body?.errors?.[0]?.message ?? 'Streaming request failed', response.status, body)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const next = await reader.read()
      if (next.done) break
      buffer += decoder.decode(next.value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      frames.forEach((frame) => {
        const event = frame.match(/^event:\s*(.+)$/m)?.[1] ?? 'message'
        const raw = frame.match(/^data:\s*(.+)$/m)?.[1]
        if (raw) onEvent(event, JSON.parse(raw) as CapabilityResponseEnvelope<TResult>)
      })
    }
  }
}
// === TASK:WP-501:END ===
