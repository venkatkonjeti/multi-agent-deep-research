import React, { useEffect, useRef } from 'react';
import type { Message, TraceEvent } from '../types';
import MessageBubble from './MessageBubble';
import AgentTrace from './AgentTrace';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatAreaProps {
  messages: Message[];
  streamingContent: string;
  liveTrace: TraceEvent[];
  isLoading: boolean;
}

export default function ChatArea({
  messages,
  streamingContent,
  liveTrace,
  isLoading,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, liveTrace]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="chat-container">
        <div className="chat-welcome">
          <div className="welcome-icon">🔬</div>
          <h2>Deep Research Agent</h2>
          <p>
            Ask any research question, paste a public URL to ingest, or upload a PDF.
            I'll search my knowledge, the web, and your documents to give you
            comprehensive, sourced answers.
          </p>
          <div style={{ display: 'flex', gap: '12px', marginTop: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['What is quantum computing?', 'https://en.wikipedia.org/wiki/CRISPR', 'Upload a PDF →'].map((hint) => (
              <span
                key={hint}
                style={{
                  padding: '8px 14px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {hint}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {/* Live agent trace while processing */}
      {isLoading && liveTrace.length > 0 && (
        <div className="message assistant" style={{ alignSelf: 'flex-start' }}>
          <div className="message-avatar">🔬</div>
          <div style={{ maxWidth: '100%', minWidth: '300px' }}>
            <AgentTrace events={liveTrace} isLive={true} />
            {streamingContent && (
              <div className="message-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamingContent}
                </ReactMarkdown>
              </div>
            )}
            {!streamingContent && (
              <div className="typing-indicator">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Loading without trace yet */}
      {isLoading && liveTrace.length === 0 && !streamingContent && (
        <div className="message assistant" style={{ alignSelf: 'flex-start' }}>
          <div className="message-avatar">🔬</div>
          <div className="typing-indicator">
            <span />
            <span />
            <span />
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
