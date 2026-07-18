import type {
  SpeechRecognitionFailure,
  SpeechRecognitionProvider,
} from './types'

interface BrowserSpeechRecognitionAlternative {
  transcript: string
}

interface BrowserSpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: BrowserSpeechRecognitionAlternative
}

interface BrowserSpeechRecognitionResultList {
  readonly length: number
  readonly [index: number]: BrowserSpeechRecognitionResult
}

interface BrowserSpeechRecognitionEvent {
  resultIndex: number
  results: BrowserSpeechRecognitionResultList
}

interface BrowserSpeechRecognitionErrorEvent {
  error: string
}

interface BrowserSpeechRecognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onstart: (() => void) | null
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

interface BrowserSpeechRecognitionConstructor {
  new (): BrowserSpeechRecognition
}

interface WebSpeechGlobalScope {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor
}

type ScopeResolver = () => WebSpeechGlobalScope | undefined

const errorMessages: Record<string, string> = {
  'not-allowed': 'Không thể dùng micro. Hãy cấp quyền micro cho trình duyệt rồi thử lại.',
  'service-not-allowed': 'Dịch vụ nhận dạng giọng nói đang bị chặn trên trình duyệt này.',
  'audio-capture': 'Không tìm thấy micro. Hãy kiểm tra thiết bị thu âm rồi thử lại.',
  network: 'Dịch vụ nhận dạng giọng nói đang mất kết nối. Hãy thử lại sau.',
  'no-speech': 'Chưa nghe thấy giọng nói. Hãy nói gần micro hơn rồi thử lại.',
  'language-not-supported': 'Trình duyệt chưa hỗ trợ nhận dạng giọng nói tiếng Việt.',
  aborted: 'Đã dừng nhận dạng giọng nói.',
}

export function appendTranscript(current: string, next: string): string {
  return [current.trim(), next.trim()].filter(Boolean).join(' ')
}

export function toSpeechRecognitionFailure(code: string): SpeechRecognitionFailure {
  return {
    code,
    message: errorMessages[code] ?? 'Không thể nhận dạng giọng nói. Hãy thử lại hoặc nhập bằng bàn phím.',
  }
}

function defaultScopeResolver(): WebSpeechGlobalScope | undefined {
  if (typeof globalThis === 'undefined') return undefined
  return globalThis as unknown as WebSpeechGlobalScope
}

export function createWebSpeechRecognitionProvider(
  resolveScope: ScopeResolver = defaultScopeResolver,
): SpeechRecognitionProvider {
  function recognitionConstructor(): BrowserSpeechRecognitionConstructor | undefined {
    const scope = resolveScope()
    return scope?.SpeechRecognition ?? scope?.webkitSpeechRecognition
  }

  return {
    isSupported: () => Boolean(recognitionConstructor()),
    create: (options, handlers) => {
      const Recognition = recognitionConstructor()
      if (!Recognition) {
        throw new Error('Speech recognition is not supported')
      }

      const recognition = new Recognition()
      let finalTranscript = ''

      recognition.lang = options.locale
      recognition.continuous = false
      recognition.interimResults = true
      recognition.maxAlternatives = 1
      recognition.onstart = handlers.onStart
      recognition.onresult = (event) => {
        const finalParts: string[] = []
        const interimParts: string[] = []

        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index]
          const alternative = result?.[0]
          if (!alternative?.transcript) continue
          if (result.isFinal) finalParts.push(alternative.transcript)
          else interimParts.push(alternative.transcript)
        }

        finalTranscript = appendTranscript(finalTranscript, finalParts.join(' '))
        const interimTranscript = interimParts.join(' ')
        const transcript = appendTranscript(finalTranscript, interimTranscript)
        if (!transcript) return

        handlers.onTranscript({
          transcript,
          isFinal: interimTranscript.length === 0,
        })
      }
      recognition.onerror = (event) => handlers.onError(toSpeechRecognitionFailure(event.error))
      recognition.onend = handlers.onEnd

      return {
        start: () => recognition.start(),
        stop: () => recognition.stop(),
        abort: () => recognition.abort(),
      }
    },
  }
}

export const webSpeechRecognitionProvider = createWebSpeechRecognitionProvider()
