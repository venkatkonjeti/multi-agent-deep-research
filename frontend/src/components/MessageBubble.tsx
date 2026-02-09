import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message as MessageType } from '../types';
import AgentTrace from './AgentTrace';

interface MessageBubbleProps {
  message: MessageType;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '🔬'}
      </div>
      <div style={{ maxWidth: '100%' }}>
        {/* Agent trace (assistant messages only) */}
        {!isUser && message.agent_trace && message.agent_trace.length > 0 && (
          <AgentTrace events={message.agent_trace} />
        )}
        <div className="message-content">
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        {/* Source badges */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div style={{ marginTop: '6px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {message.sources.slice(0, 5).map((source, idx) => (
              <span
                key={idx}
                style={{
                  fontSize: '10px',
                  padding: '2px 8px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '10px',
                  color: 'var(--text-muted)',
                }}
              >
                {source.length > 40 ? source.slice(0, 40) + '…' : source}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
