export interface SpeechTranscriptUpdate {
  transcript: string
  isFinal: boolean
}

export interface SpeechRecognitionFailure {
  code: string
  message: string
}

export interface SpeechRecognitionHandlers {
  onStart: () => void
  onTranscript: (update: SpeechTranscriptUpdate) => void
  onError: (failure: SpeechRecognitionFailure) => void
  onEnd: () => void
}

export interface SpeechRecognitionOptions {
  locale: string
}

export interface SpeechRecognitionSession {
  start: () => void
  stop: () => void
  abort: () => void
}

export interface SpeechRecognitionProvider {
  isSupported: () => boolean
  create: (
    options: SpeechRecognitionOptions,
    handlers: SpeechRecognitionHandlers,
  ) => SpeechRecognitionSession
}
