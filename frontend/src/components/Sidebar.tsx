import React, { useEffect, useRef, useState } from 'react';
import type { Conversation } from '../types';
import { FiPlus, FiTrash2, FiDatabase, FiMessageSquare, FiSearch, FiCheck, FiX } from 'react-icons/fi';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSearch: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  vectorStats: Record<string, number>;
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSearch,
  onRename,
  onDelete,
  vectorStats,
}: SidebarProps) {
  const totalDocs = Object.values(vectorStats).reduce((a, b) => a + b, 0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus the rename input when editing starts
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const startRename = (conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const commitRename = () => {
    if (editingId && editTitle.trim()) {
      onRename(editingId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditTitle('');
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="logo">🔬</span>
        <h1>Deep Research</h1>
      </div>

      <div className="sidebar-actions">
        <button className="new-chat-btn" onClick={onNew}>
          <FiPlus size={16} />
          New Research
        </button>
        <button className="search-btn" onClick={onSearch} title="Search conversations (Ctrl+K)">
          <FiSearch size={16} />
        </button>
      </div>

      <div className="conversation-list">
        {conversations.map((conv) => (
          <div
            key={conv.id}
            className={`conversation-item ${conv.id === activeId ? 'active flash-highlight' : ''}`}
            onClick={() => {
              if (editingId !== conv.id) onSelect(conv.id);
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              startRename(conv);
            }}
          >
            <FiMessageSquare size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
            {editingId === conv.id ? (
              <input
                ref={inputRef}
                className="rename-input"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename();
                  if (e.key === 'Escape') cancelRename();
                }}
                onBlur={commitRename}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="title">{conv.title}</span>
            )}
            <button
              className="delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(conv.id);
              }}
              title="Delete conversation"
            >
              <FiTrash2 size={13} />
            </button>
          </div>
        ))}
        {conversations.length === 0 && (
          <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
            No conversations yet
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-stats">
          <span><FiDatabase size={11} /> {totalDocs} docs</span>
          <span>{conversations.length} chats</span>
        </div>
      </div>
    </aside>
  );
}
