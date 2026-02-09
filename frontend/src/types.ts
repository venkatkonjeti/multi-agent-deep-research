/* ─── TypeScript types for the Deep Research Agent frontend ─── */

export interface Conversation {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sources: string[];
  agent_trace: TraceEvent[];
  timestamp: number;
}

export interface TraceEvent {
  event_type: string;
  agent_name: string;
  message: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface UploadResult {
  success: boolean;
  filename: string;
  pages: number;
  chunks_stored: number;
  images_processed: number;
  tables_found: number;
  error?: string;
  trace: TraceEvent[];
}

export interface HealthStatus {
  status: string;
  ollama: {
    status: string;
    models?: string[];
    inference_model_available?: boolean;
    embedding_model_available?: boolean;
    error?: string;
  };
  vector_db: Record<string, number>;
}
