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
  information_assistance: '/v1/capabilities/information-assistance',
  emergency_safety: '/v1/capabilities/emergency-safety',
  appointment_booking: '/v1/capabilities/appointment-booking',
  appointment_status: '/v1/capabilities/appointment-status',
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
    this.fetcher = options.fetcher ?? fetch
    this.defaultContext = options.defaultContext ?? defaultClientContext
  }

  async send<TPayload extends Record<string, unknown>, TResult = unknown>(
    request: ChatClientRequest<TPayload>,
  ): Promise<CapabilityResponseEnvelope<TResult>> {
    const response = await this.fetcher(`${this.baseUrl}${capabilityPath[request.capability]}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
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
}
// === TASK:WP-501:END ===
