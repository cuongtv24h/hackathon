// === TASK:WP-501:START ===
export interface SSEMessage<TData = unknown> {
  event: string
  data: TData
}

export interface SSEClientOptions<TData = unknown> {
  eventSourceFactory?: (url: string) => EventSource
  onMessage: (message: SSEMessage<TData>) => void
  onError?: (error: Event) => void
}

export class SSEClient<TData = unknown> {
  private readonly eventSourceFactory: (url: string) => EventSource
  private readonly onMessage: (message: SSEMessage<TData>) => void
  private readonly onError?: (error: Event) => void
  private source?: EventSource

  constructor(options: SSEClientOptions<TData>) {
    this.eventSourceFactory = options.eventSourceFactory ?? ((url: string) => new EventSource(url))
    this.onMessage = options.onMessage
    this.onError = options.onError
  }

  connect(url: string): void {
    this.close()
    this.source = this.eventSourceFactory(url)
    const forwardMessage = (event: MessageEvent) => {
      try {
        this.onMessage({ event: event.type || 'message', data: JSON.parse(event.data) as TData })
      } catch {
        this.onError?.(event as unknown as Event)
      }
    }
    this.source.onmessage = forwardMessage
    ;['ack', 'status', 'content_delta', 'tool_status', 'citation', 'action', 'completed', 'error'].forEach((eventName) => {
      this.source?.addEventListener(eventName, forwardMessage)
    })
    this.source.onerror = (event) => {
      this.onError?.(event)
    }
  }

  close(): void {
    if (this.source) {
      this.source.close()
      this.source = undefined
    }
  }
}
// === TASK:WP-501:END ===
