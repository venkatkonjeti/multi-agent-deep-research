import React, { useState } from 'react';
import type { TraceEvent } from '../types';
import { FiChevronDown, FiChevronRight } from 'react-icons/fi';

interface AgentTraceProps {
  events: TraceEvent[];
  isLive?: boolean;
}

const ICONS: Record<string, string> = {
  agent_start: '⚡',
  agent_progress: '🔄',
  agent_result: '✅',
  agent_error: '❌',
  plan_step: '📋',
  stream_token: '✍️',
  stream_end: '🏁',
};

const AGENT_LABELS: Record<string, string> = {
  orchestrator: 'Orchestrator',
  retrieval: 'Retrieval Agent',
  knowledge: 'Knowledge Agent',
  web_search: 'Web Search Agent',
  ingestion: 'Ingestion Agent',
  synthesis: 'Synthesis Agent',
};

export default function AgentTrace({ events, isLive }: AgentTraceProps) {
  const [expanded, setExpanded] = useState(true);

  // Filter out stream tokens for the trace display
  const traceEvents = events.filter(
    (e) => e.event_type !== 'stream_token' && e.event_type !== 'stream_end'
  );

  if (traceEvents.length === 0) return null;

  return (
    <div className="agent-trace">
      <div className="agent-trace-header" onClick={() => setExpanded(!expanded)}>
        <span>
          {isLive ? '🔄 ' : '📋 '}
          Agent Activity ({traceEvents.length} steps)
        </span>
        {expanded ? <FiChevronDown size={14} /> : <FiChevronRight size={14} />}
      </div>
      {expanded && (
        <div className="agent-trace-body">
          {traceEvents.map((event, idx) => (
            <div key={idx} className={`trace-step ${event.event_type}`}>
              <span className="trace-icon">
                {ICONS[event.event_type] || '•'}
              </span>
              <span>
                <strong>{AGENT_LABELS[event.agent_name] || event.agent_name}</strong>
                {': '}
                {event.message}
              </span>
            </div>
          ))}
          {isLive && (
            <div className="trace-step" style={{ color: 'var(--info)' }}>
              <span className="trace-icon">⏳</span>
              <span>Processing...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
