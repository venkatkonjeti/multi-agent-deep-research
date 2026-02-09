import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Conversation, Message, TraceEvent } from './types';
import * as api from './api';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import InputBar from './components/InputBar';
import SearchModal from './components/SearchModal';

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const [vectorStats, setVectorStats] = useState<Record<string, number>>({});
  const [showSearch, setShowSearch] = useState(false);

  // Ctrl+K / Cmd+K keyboard shortcut to open search
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setShowSearch((v) => !v);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // Keep a ref so async callbacks always see the latest activeConvId
  const activeConvRef = useRef<string | null>(null);
  activeConvRef.current = activeConvId;

  // ─── Load conversations on mount ────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const convs = await api.listConversations();
        setConversations(convs);
        // Auto-select the most recent conversation
        if (convs.length > 0) {
          const mostRecent = convs[0]; // already sorted by updated_at DESC
          setActiveConvId(mostRecent.id);
          activeConvRef.current = mostRecent.id;
          const msgs = await api.getMessages(mostRecent.id);
          setMessages(msgs);
        }
      } catch (err) {
        console.error('Failed to load conversations:', err);
      }
    })();
    loadVectorStats();
  }, []);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  };

  const loadVectorStats = async () => {
    try {
      const health = await api.getHealth();
      setVectorStats(health.vector_db || {});
    } catch {
      // silent
    }
  };

  const loadMessages = useCallback(async (convId: string) => {
    try {
      const msgs = await api.getMessages(convId);
      setMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }, []);

  // ─── Select conversation ────────────────────────────────
  const selectConversation = useCallback(
    (id: string) => {
      setActiveConvId(id);
      setStreamingContent('');
      setLiveTrace([]);
      loadMessages(id);
    },
    [loadMessages]
  );

  // ─── New conversation ──────────────────────────────────
  // Returns the new conversation ID for callers that need it immediately
  const newConversation = async (): Promise<string | null> => {
    try {
      const conv = await api.createConversation();
      setConversations((prev) => [conv, ...prev]);
      setActiveConvId(conv.id);
      activeConvRef.current = conv.id;
      setMessages([]);
      setStreamingContent('');
      setLiveTrace([]);
      return conv.id;
    } catch (err) {
      console.error('Failed to create conversation:', err);
      return null;
    }
  };

  // ─── Rename conversation ──────────────────────────────
  const renameConversation = async (id: string, title: string) => {
    try {
      await api.renameConversation(id, title);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === id ? { ...c, title, updated_at: Date.now() / 1000 } : c
        )
      );
    } catch (err) {
      console.error('Failed to rename conversation:', err);
    }
  };

  // ─── Delete conversation ───────────────────────────────
  const deleteConversation = async (id: string) => {
    try {
      await api.deleteConversation(id);
      setConversations((prev) => {
        const remaining = prev.filter((c) => c.id !== id);
        // If we deleted the active one, select the next most recent
        if (activeConvRef.current === id) {
          if (remaining.length > 0) {
            setActiveConvId(remaining[0].id);
            activeConvRef.current = remaining[0].id;
            loadMessages(remaining[0].id);
          } else {
            setActiveConvId(null);
            activeConvRef.current = null;
            setMessages([]);
          }
        }
        return remaining;
      });
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  // ─── Send message (accepts optional explicit convId) ───
  const sendMessage = async (message: string, explicitConvId?: string) => {
    const convId = explicitConvId ?? activeConvRef.current;
    if (!convId || isLoading) return;

    // Add user message optimistically
    const userMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: convId,
      role: 'user',
      content: message,
      sources: [],
      agent_trace: [],
      timestamp: Date.now() / 1000,
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);
    setStreamingContent('');
    setLiveTrace([]);

    try {
      let fullResponse = '';

      await api.sendChatMessage(convId, message, {
        onTrace: (event) => {
          setLiveTrace((prev) => [...prev, event]);
        },
        onToken: (token) => {
          fullResponse += token;
          setStreamingContent(fullResponse);
        },
        onFullResponse: (msg) => {
          fullResponse = msg;
          setStreamingContent(msg);
        },
        onDone: () => {
          // Reload messages to get the saved assistant message with trace
          loadMessages(convId);
          setStreamingContent('');
          setLiveTrace([]);
          setIsLoading(false);
          // Refresh conversations (title may have changed)
          loadConversations();
          loadVectorStats();
        },
        onError: (error) => {
          console.error('Chat error:', error);
          const errMsg: Message = {
            id: `err-${Date.now()}`,
            conversation_id: convId,
            role: 'assistant',
            content: `❌ Error: ${error}`,
            sources: [],
            agent_trace: [],
            timestamp: Date.now() / 1000,
          };
          setMessages((prev) => [...prev, errMsg]);
          setIsLoading(false);
          setStreamingContent('');
          setLiveTrace([]);
        },
      });
    } catch (err) {
      console.error('Send failed:', err);
      setIsLoading(false);
    }
  };

  // ─── Upload PDF (accepts optional explicit convId) ─────
  const uploadPDF = async (file: File, explicitConvId?: string) => {
    const convId = explicitConvId ?? activeConvRef.current;
    if (!convId) return;

    setIsLoading(true);
    setLiveTrace([
      {
        event_type: 'plan_step',
        agent_name: 'orchestrator',
        message: `Uploading and processing: ${file.name}`,
        data: {},
        timestamp: Date.now() / 1000,
      },
    ]);

    try {
      const result = await api.uploadPDF(convId, file);
      setLiveTrace(result.trace || []);

      // Reload messages to see the upload confirmation
      await loadMessages(convId);
      loadVectorStats();
    } catch (err) {
      console.error('Upload failed:', err);
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        conversation_id: convId,
        role: 'assistant',
        content: `❌ Upload failed: ${err}`,
        sources: [],
        agent_trace: [],
        timestamp: Date.now() / 1000,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
      setLiveTrace([]);
    }
  };

  // ─── Handle send when no conversation selected ────────
  const handleSendNoConv = async (message: string) => {
    const newId = await newConversation();
    if (newId) {
      sendMessage(message, newId);
    }
  };

  const handleUploadNoConv = async (file: File) => {
    const newId = await newConversation();
    if (newId) {
      uploadPDF(file, newId);
    }
  };

  return (
    <div className="app-layout">
      <Sidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={selectConversation}
        onNew={newConversation}
        onSearch={() => setShowSearch(true)}
        onRename={renameConversation}
        onDelete={deleteConversation}
        vectorStats={vectorStats}
      />
      {showSearch && (
        <SearchModal
          conversations={conversations}
          onSelect={selectConversation}
          onClose={() => setShowSearch(false)}
        />
      )}
      <div className="main-area">
        {activeConvId ? (
          <>
            <ChatArea
              messages={messages}
              streamingContent={streamingContent}
              liveTrace={liveTrace}
              isLoading={isLoading}
            />
            <InputBar
              onSend={sendMessage}
              onUpload={uploadPDF}
              disabled={isLoading}
            />
          </>
        ) : (
          <>
            <ChatArea
              messages={[]}
              streamingContent=""
              liveTrace={[]}
              isLoading={false}
            />
            <InputBar
              onSend={handleSendNoConv}
              onUpload={handleUploadNoConv}
              disabled={false}
            />
          </>
        )}
      </div>
    </div>
  );
}
