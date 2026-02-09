import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { Conversation } from '../types';
import { FiSearch, FiMessageSquare, FiX } from 'react-icons/fi';

interface SearchModalProps {
  conversations: Conversation[];
  onSelect: (id: string) => void;
  onClose: () => void;
}

export default function SearchModal({ conversations, onSelect, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus on open
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close on Escape or outside click
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Filter conversations
  const filtered = useMemo(() => {
    if (!query.trim()) return conversations;
    const q = query.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [query, conversations]);

  // Reset selection when results change
  useEffect(() => {
    setSelectedIdx(0);
  }, [filtered]);

  // Scroll selected item into view
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const item = list.children[selectedIdx] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [selectedIdx]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filtered.length > 0) {
      e.preventDefault();
      handleSelect(filtered[selectedIdx].id);
    }
  };

  const handleSelect = (id: string) => {
    onSelect(id);
    onClose();
  };

  // Highlight matching text
  const highlight = (text: string) => {
    if (!query.trim()) return text;
    const q = query.trim();
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="search-highlight">{text.slice(idx, idx + q.length)}</mark>
        {text.slice(idx + q.length)}
      </>
    );
  };

  const formatDate = (ts: number) => {
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="search-input-wrapper">
          <FiSearch size={18} className="search-input-icon" />
          <input
            ref={inputRef}
            className="search-input"
            type="text"
            placeholder="Search conversations..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          {query && (
            <button className="search-clear-btn" onClick={() => setQuery('')}>
              <FiX size={14} />
            </button>
          )}
        </div>

        <div className="search-results" ref={listRef}>
          {filtered.length > 0 ? (
            filtered.map((conv, idx) => (
              <div
                key={conv.id}
                className={`search-result-item ${idx === selectedIdx ? 'selected' : ''}`}
                onClick={() => handleSelect(conv.id)}
                onMouseEnter={() => setSelectedIdx(idx)}
              >
                <FiMessageSquare size={14} className="search-result-icon" />
                <div className="search-result-text">
                  <span className="search-result-title">{highlight(conv.title)}</span>
                  <span className="search-result-date">{formatDate(conv.updated_at)}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="search-no-results">
              {query ? `No conversations matching "${query}"` : 'No conversations yet'}
            </div>
          )}
        </div>

        <div className="search-footer">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
