export interface StepEvent {
  name: string
  ms: number
  detail: string
}

export interface Citation {
  no: number
  chunk_id: string
  text: string
  source: string
  section_path: string
  page: number
}

export interface DonePayload {
  route: 'answered' | 'safe' | 'fallback'
  answer: string
  citations: Citation[]
  conversation_id: number
  message_id: number
  latency_ms: number
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  latency_ms: number | null
  created_at: string
}

export interface KbDocument {
  id: number
  doc_hash: string
  source: string
  title: string
  doc_type: string
  department: string
  chunk_count: number
  updated_at: string
}

export interface IngestJobInfo {
  id: number
  status: string
  total_docs: number
  processed_docs: number
  total_chunks: number
  error: string | null
  created_at: string
}

export interface ChunkSample {
  chunk_id: string
  text: string
  section_path: string
  seq: number
}
