import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  SpeechRecognitionProvider,
  SpeechRecognitionSession,
} from './types'
import {
  appendTranscript,
  webSpeechRecognitionProvider,
} from './webSpeechRecognition'

type SpeechInputState = 'idle' | 'listening' | 'stopping' | 'complete' | 'error' | 'unsupported'

export interface SpeechInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  locale?: string
  provider?: SpeechRecognitionProvider
}

const idleMessage = 'Nhấn micro để nói. Bạn có thể sửa nội dung trước khi gửi.'
const unsupportedMessage = 'Trình duyệt chưa hỗ trợ nhập bằng giọng nói. Bạn vẫn có thể dùng bàn phím.'

export function SpeechInput({
  value,
  onChange,
  disabled = false,
  locale = 'vi-VN',
  provider = webSpeechRecognitionProvider,
}: SpeechInputProps) {
  const supported = useMemo(() => provider.isSupported(), [provider])
  const [state, setState] = useState<SpeechInputState>(supported ? 'idle' : 'unsupported')
  const [message, setMessage] = useState(supported ? idleMessage : unsupportedMessage)
  const sessionRef = useRef<SpeechRecognitionSession | null>(null)
  const baseTranscriptRef = useRef('')
  const receivedTranscriptRef = useRef(false)
  const recognitionFailedRef = useRef(false)
  const mountedRef = useRef(true)
  const sessionGenerationRef = useRef(0)

  const active = state === 'listening' || state === 'stopping'

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      sessionGenerationRef.current += 1
      const session = sessionRef.current
      sessionRef.current = null
      session?.abort()
    }
  }, [])

  useEffect(() => {
    if (!disabled || !sessionRef.current) return
    sessionGenerationRef.current += 1
    const session = sessionRef.current
    sessionRef.current = null
    session.abort()
    setState('idle')
    setMessage(idleMessage)
  }, [disabled])

  function startRecognition() {
    if (!supported || disabled || sessionRef.current) return

    baseTranscriptRef.current = value
    receivedTranscriptRef.current = false
    recognitionFailedRef.current = false
    const sessionGeneration = sessionGenerationRef.current + 1
    sessionGenerationRef.current = sessionGeneration
    const isCurrentSession = () => (
      mountedRef.current && sessionGenerationRef.current === sessionGeneration
    )
    setState('listening')
    setMessage('Đang mở micro…')

    try {
      const session = provider.create({ locale }, {
        onStart: () => {
          if (!isCurrentSession()) return
          setState('listening')
          setMessage('Đang nghe… Hãy nói câu hỏi của bạn.')
        },
        onTranscript: (update) => {
          if (!isCurrentSession()) return
          receivedTranscriptRef.current = true
          onChange(appendTranscript(baseTranscriptRef.current, update.transcript))
          setMessage(update.isFinal
            ? 'Đã nhận giọng nói. Hãy kiểm tra nội dung trước khi gửi.'
            : 'Đang nghe và tạo bản nháp…')
        },
        onError: (failure) => {
          if (!isCurrentSession()) return
          recognitionFailedRef.current = true
          setState('error')
          setMessage(failure.message)
        },
        onEnd: () => {
          if (!isCurrentSession()) return
          sessionRef.current = null
          if (recognitionFailedRef.current) return
          if (receivedTranscriptRef.current) {
            setState('complete')
            setMessage('Đã điền bản ghi vào ô nhập. Bạn có thể sửa trước khi gửi.')
          } else {
            setState('idle')
            setMessage('Đã dừng. Chưa nhận được nội dung; hãy thử lại hoặc dùng bàn phím.')
          }
        },
      })
      sessionRef.current = session
      session.start()
    } catch {
      sessionGenerationRef.current += 1
      sessionRef.current = null
      setState('error')
      setMessage('Không thể khởi động micro. Hãy kiểm tra quyền truy cập rồi thử lại.')
    }
  }

  function stopRecognition() {
    const session = sessionRef.current
    if (!session) return
    setState('stopping')
    setMessage('Đang hoàn tất bản ghi…')
    try {
      session.stop()
    } catch {
      sessionGenerationRef.current += 1
      sessionRef.current = null
      setState('error')
      setMessage('Không thể hoàn tất nhận dạng giọng nói. Hãy thử lại.')
    }
  }

  return (
    <div className="speech-input" data-state={state}>
      <button
        type="button"
        className="speech-input-button"
        aria-label={active ? 'Dừng nhập bằng giọng nói' : 'Bắt đầu nhập bằng giọng nói'}
        aria-pressed={active}
        disabled={disabled || !supported}
        onClick={active ? stopRecognition : startRecognition}
        title={supported ? 'Nhập câu hỏi bằng giọng nói' : unsupportedMessage}
      >
        {active ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="7" y="7" width="10" height="10" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
          </svg>
        )}
      </button>
      <span className="speech-input-status" aria-live="polite" aria-atomic="true">
        {message}
      </span>
    </div>
  )
}
