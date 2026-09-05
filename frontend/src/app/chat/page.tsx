'use client';
import { useState, useEffect, useRef, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import FileUploader from '@/components/FileUploader';

interface AttachedFile {
  id: string;
  name: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  file_id?: string | null;
  created_at: string;
}

interface Conversation {
  id: string;
  title: string;
  model_used: string;
  created_at: string;
  updated_at: string;
}

export default function ChatPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [showUploader, setShowUploader] = useState(false);
  const [useRag, setUseRag] = useState(true);
  const [retrievedCount, setRetrievedCount] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push('/login');
  }, [authLoading, user, router]);

  useEffect(() => {
    if (user) loadConversations();
  }, [user]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamText]);

  const loadConversations = async () => {
    try {
      const data = await api.get('/api/chat/conversations');
      setConversations(data);
    } catch {}
  };

  const selectConversation = async (id: string) => {
    setActiveConvId(id);
    setStreamText('');
    try {
      const data = await api.get(`/api/chat/conversations/${id}`);
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    }
  };

  const newChat = () => {
    setActiveConvId(null);
    setMessages([]);
    setStreamText('');
    setAttachedFiles([]);
  };

  const deleteConversation = async (id: string) => {
    try {
      await api.delete(`/api/chat/conversations/${id}`);
      if (activeConvId === id) newChat();
      loadConversations();
    } catch {}
  };

  const handleFileUploaded = useCallback((fileId: string) => {
    setAttachedFiles((prev) => [...prev, { id: fileId, name: '文件已上传' }]);
    setShowUploader(false);
  }, []);

  const handleFileUploadedDetail = useCallback((detail: { id: string; name: string }) => {
    // Avoid duplicate files
    setAttachedFiles((prev) => {
      if (prev.some((f) => f.id === detail.id)) return prev;
      return [...prev, { id: detail.id, name: detail.name }];
    });
    setShowUploader(false);
  }, []);

  const removeAttachedFile = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const handleStop = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      // Keep whatever text has been received so far as a partial response
      if (streamText) {
        const partialMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: streamText + '\n\n*[用户中断]*',
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, partialMsg]);
      }
      setStreamText('');
      setStreaming(false);
    }
  };

  const handleSend = useCallback(async (e?: FormEvent) => {
    if (e) e.preventDefault();
    const text = input.trim();
    if ((!text && attachedFiles.length === 0) || streaming) return;
    setInput('');
    setStreaming(true);
    setStreamText('');
    setRetrievedCount(null);

    const displayContent = text || (attachedFiles.length > 0 ? `[发送了 ${attachedFiles.length} 个文件]` : '');

    const tempUserMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: displayContent,
      file_id: attachedFiles.map((f) => f.id).join(',') || null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    const currentFileIds = attachedFiles.map((f) => f.id);
    setAttachedFiles([]);

    let fullResponse = '';

    abortRef.current = api.streamChat(
      '/api/chat/send',
      {
        conversation_id: activeConvId || undefined,
        message: text || '请分析这些文件的内容',
        file_ids: currentFileIds.length > 0 ? currentFileIds : undefined,
        use_rag: useRag,
      },
      (chunk: string) => {
        fullResponse += chunk;
        setStreamText(fullResponse);
      },
      (convId?: string, retrieved?: number) => {
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: fullResponse,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamText('');
        setStreaming(false);
        setRetrievedCount(retrieved ?? null);
        abortRef.current = null;
        if (convId && !activeConvId) {
          setActiveConvId(convId);
          loadConversations();
        }
        if (activeConvId) loadConversations();
      },
      (err: string) => {
        setStreamText(err);
        setStreaming(false);
        abortRef.current = null;
      },
    );
  }, [input, streaming, activeConvId, attachedFiles]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (authLoading) return null;
  if (!user) return null;

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-72' : 'w-0'} transition-all duration-200 bg-gray-50 border-r border-gray-200 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-200">
          <button
            onClick={newChat}
            className="w-full py-2.5 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors text-sm"
          >
            + {t('chat.new')}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`group flex items-center rounded-lg transition-colors ${
                activeConvId === conv.id ? 'bg-indigo-50' : 'hover:bg-gray-100'
              }`}
            >
              <button
                onClick={() => selectConversation(conv.id)}
                className="flex-1 text-left px-3 py-2.5 text-sm text-gray-700 truncate"
              >
                {conv.title}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 transition-all"
                title={t('chat.delete')}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat header */}
        <div className="flex items-center h-14 px-4 border-b border-gray-200 bg-white">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 text-gray-500 hover:text-indigo-600 rounded-lg hover:bg-gray-100 mr-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <Link href="/dashboard" className="p-2 text-gray-500 hover:text-indigo-600 rounded-lg hover:bg-gray-100 mr-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <h2 className="font-medium text-gray-700 text-sm truncate">
            {activeConvId ? conversations.find((c) => c.id === activeConvId)?.title || t('nav.chat') : t('chat.new')}
          </h2>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-white">
          {messages.length === 0 && !streaming && (
            <div className="flex items-center justify-center h-full text-gray-400">
              <div className="text-center">
                <div className="text-5xl mb-4">&#x1F4AC;</div>
                <p className="text-sm">{t('chat.empty')}</p>
                <p className="text-xs text-gray-300 mt-2">支持上传多个文件进行分析讨论</p>
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-md'
                  : 'bg-gray-100 text-gray-800 rounded-bl-md'
              }`}>
                {msg.file_id && (
                  <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-white/20">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                    <span className="text-xs opacity-80">
                      &#x1F4CE; {msg.file_id.split(',').length > 1 ? `${msg.file_id.split(',').length} 个文件` : '文件'}
                    </span>
                  </div>
                )}
                <div className="whitespace-pre-wrap">{msg.content}</div>
              </div>
            </div>
          ))}
          {streaming && (
            <div className="flex justify-start">
              <div className="max-w-[75%] bg-gray-100 text-gray-800 rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed">
                <div className="whitespace-pre-wrap">
                  {streamText || (
                    <div className="flex space-x-1.5">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-gray-200 bg-white">
          {/* RAG retrieval status */}
          {retrievedCount != null && retrievedCount > 0 && (
            <div className="mb-2 flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 w-fit">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              本次回答基于 {retrievedCount} 个检索到的文献片段
            </div>
          )}

          {/* File upload drop zone */}
          {showUploader && (
            <div className="mb-3">
              <FileUploader
                onUpload={handleFileUploaded}
                onUploadDetail={handleFileUploadedDetail}
                accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls,.py,.json,.pptx"
              />
            </div>
          )}

          {/* Attached files bar */}
          {attachedFiles.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {attachedFiles.map((file) => (
                <div key={file.id} className="flex items-center gap-1.5 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5">
                  <svg className="w-3.5 h-3.5 text-indigo-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="text-xs text-indigo-700 truncate max-w-32">{file.name}</span>
                  <button
                    onClick={() => removeAttachedFile(file.id)}
                    className="text-indigo-400 hover:text-red-500 transition-colors ml-0.5"
                    title="移除"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            {/* RAG retrieval-augmentation toggle */}
            <button
              type="button"
              onClick={() => setUseRag(!useRag)}
              className={`px-3 py-3 rounded-xl text-xs font-medium transition-colors flex items-center gap-1 ${
                useRag
                  ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title={useRag ? '检索增强已开启：回答将基于你已索引的文献' : '检索增强已关闭'}
              disabled={streaming}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M11 18a7 7 0 110-14 7 7 0 010 14z" />
              </svg>
              RAG
            </button>

            {/* File attach button */}
            <button
              type="button"
              onClick={() => setShowUploader(!showUploader)}
              className={`p-3 rounded-xl transition-colors ${
                showUploader
                  ? 'bg-indigo-100 text-indigo-600'
                  : 'text-gray-400 hover:text-indigo-600 hover:bg-gray-100'
              }`}
              title="上传文件（支持多个）"
              disabled={streaming}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>

            {/* Text input */}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={attachedFiles.length > 0 ? '输入关于文件的问题，或直接发送...' : t('chat.placeholder')}
              className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none max-h-32"
              rows={1}
              disabled={streaming}
            />

            {/* Stop button (during streaming) or Send button */}
            {streaming ? (
              <button
                type="button"
                onClick={handleStop}
                className="p-3 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-colors flex-shrink-0"
                title="暂停生成"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="4" y="4" width="6" height="16" rx="1" />
                  <rect x="14" y="4" width="6" height="16" rx="1" />
                </svg>
              </button>
            ) : (
              <button
                type="submit"
                onClick={handleSend}
                disabled={(!input.trim() && attachedFiles.length === 0)}
                className="p-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
