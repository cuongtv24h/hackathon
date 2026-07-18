import { describe, expect, it, vi } from 'vitest'
import {
  appendTranscript,
  createWebSpeechRecognitionProvider,
  toSpeechRecognitionFailure,
} from './webSpeechRecognition'

interface FakeResult {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: { transcript: string }
}

interface FakeResultList {
  readonly length: number
  readonly [index: number]: FakeResult
}

interface FakeResultEvent {
  resultIndex: number
  results: FakeResultList
}

class FakeSpeechRecognition {
  static instance: FakeSpeechRecognition

  lang = ''
  continuous = true
  interimResults = false
  maxAlternatives = 0
  onstart: (() => void) | null = null
  onresult: ((event: FakeResultEvent) => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  start = vi.fn(() => this.onstart?.())
  stop = vi.fn(() => this.onend?.())
  abort = vi.fn()

  constructor() {
    FakeSpeechRecognition.instance = this
  }

  emitResults(...parts: Array<{ transcript: string; isFinal: boolean }>) {
    const results = parts.map((part) => ({
      0: { transcript: part.transcript },
      isFinal: part.isFinal,
      length: 1,
    })) as unknown as FakeResultList
    this.onresult?.({ resultIndex: 0, results })
  }
}

function createProvider() {
  return createWebSpeechRecognitionProvider(() => ({
    SpeechRecognition: FakeSpeechRecognition,
  }))
}

describe('webSpeechRecognitionProvider', () => {
  it('configures a short Vietnamese recognition session and combines interim results', () => {
    const onStart = vi.fn()
    const onTranscript = vi.fn()
    const onError = vi.fn()
    const onEnd = vi.fn()
    const provider = createProvider()

    expect(provider.isSupported()).toBe(true)
    const session = provider.create({ locale: 'vi-VN' }, {
      onStart,
      onTranscript,
      onError,
      onEnd,
    })
    session.start()

    const recognition = FakeSpeechRecognition.instance
    expect(recognition.lang).toBe('vi-VN')
    expect(recognition.continuous).toBe(false)
    expect(recognition.interimResults).toBe(true)
    expect(recognition.maxAlternatives).toBe(1)
    expect(onStart).toHaveBeenCalledOnce()

    recognition.emitResults(
      { transcript: 'Tôi muốn', isFinal: true },
      { transcript: 'đặt lịch', isFinal: false },
    )
    expect(onTranscript).toHaveBeenLastCalledWith({
      transcript: 'Tôi muốn đặt lịch',
      isFinal: false,
    })

    recognition.emitResults({ transcript: 'đặt lịch khám', isFinal: true })
    expect(onTranscript).toHaveBeenLastCalledWith({
      transcript: 'Tôi muốn đặt lịch khám',
      isFinal: true,
    })
  })

  it('maps browser failures to actionable Vietnamese messages', () => {
    expect(toSpeechRecognitionFailure('not-allowed')).toEqual({
      code: 'not-allowed',
      message: 'Không thể dùng micro. Hãy cấp quyền micro cho trình duyệt rồi thử lại.',
    })
    expect(toSpeechRecognitionFailure('unknown').message).toMatch(/nhập bằng bàn phím/i)
  })

  it('reports unsupported browsers without constructing a session', () => {
    const provider = createWebSpeechRecognitionProvider(() => ({}))

    expect(provider.isSupported()).toBe(false)
    expect(() => provider.create({ locale: 'vi-VN' }, {
      onStart: vi.fn(),
      onTranscript: vi.fn(),
      onError: vi.fn(),
      onEnd: vi.fn(),
    })).toThrow(/not supported/i)
  })
})

describe('appendTranscript', () => {
  it('preserves existing typed content without adding duplicate whitespace', () => {
    expect(appendTranscript('  Tôi cần ', ' đặt lịch  ')).toBe('Tôi cần đặt lịch')
    expect(appendTranscript('', 'Giờ khám')).toBe('Giờ khám')
  })
})
