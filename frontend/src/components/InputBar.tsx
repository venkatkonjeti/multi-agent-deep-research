import React, { useRef, useState } from 'react';
import { FiSend, FiPaperclip, FiX } from 'react-icons/fi';

interface InputBarProps {
  onSend: (message: string) => void;
  onUpload: (file: File) => void;
  disabled: boolean;
}

export default function InputBar({ onSend, onUpload, disabled }: InputBarProps) {
  const [text, setText] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    if (pendingFile) {
      onUpload(pendingFile);
      setPendingFile(null);
      return;
    }
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-resize
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setPendingFile(file);
    }
    // Reset input
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="input-area">
      {pendingFile && (
        <div className="upload-indicator">
          📄 {pendingFile.name} ({(pendingFile.size / 1024).toFixed(0)} KB)
          <span className="remove" onClick={() => setPendingFile(null)}>
            <FiX size={14} />
          </span>
        </div>
      )}
      <div className="input-wrapper">
        <input
          type="file"
          ref={fileInputRef}
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={handleFileSelect}
        />
        <button
          className="icon-btn"
          onClick={() => fileInputRef.current?.click()}
          title="Upload PDF"
          disabled={disabled}
        >
          <FiPaperclip />
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={pendingFile ? 'Press Send to upload PDF...' : 'Ask a research question, paste a URL, or upload a PDF...'}
          disabled={disabled}
          rows={1}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={disabled || (!text.trim() && !pendingFile)}
          title="Send"
        >
          <FiSend />
        </button>
      </div>
    </div>
  );
}
