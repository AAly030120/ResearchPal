'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface FileInfo {
  id: string;
  original_name: string;
  file_type: string;
  file_size: number;
  version: number;
}

interface FileVersion {
  id: string;
  version: number;
  file_size: number;
  uploaded_at: string;
}

interface FilePreviewModalProps {
  file: FileInfo | null;
  onClose: () => void;
}

export default function FilePreviewModal({ file, onClose }: FilePreviewModalProps) {
  const [activeTab, setActiveTab] = useState<'preview' | 'versions'>('preview');
  const [versions, setVersions] = useState<FileVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  useEffect(() => {
    if (!file) return;
    setActiveTab('preview');
    setVersions([]);
  }, [file]);

  const loadVersions = async () => {
    if (!file) return;
    setLoadingVersions(true);
    try {
      const data = await api.get(`/api/files/versions/${file.id}`);
      setVersions(Array.isArray(data) ? data : []);
    } catch {
      // ignore
    } finally {
      setLoadingVersions(false);
    }
  };

  const handleTabSwitch = (tab: 'preview' | 'versions') => {
    setActiveTab(tab);
    if (tab === 'versions' && versions.length === 0) loadVersions();
  };

  if (!file) return null;

  const previewUrl = api.getPreviewUrl(file.id);
  const downloadUrl = api.getDownloadUrl(file.id);
  const isImage = ['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(file.file_type);
  const isPDF = file.file_type === 'pdf';
  const isText = ['txt', 'md', 'json', 'csv', 'py', 'log', 'html'].includes(file.file_type);
  const canPreview = isImage || isPDF || isText;

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (d: string) => {
    try { return new Date(d).toLocaleString('zh-CN'); } catch { return d; }
  };

  const handleCopyLink = () => {
    const url = `${window.location.origin}/api/files/download/${file.id}`;
    navigator.clipboard.writeText(url).then(() => {
      // Brief feedback
      const btn = document.activeElement as HTMLElement;
      if (btn) {
        const orig = btn.textContent;
        btn.textContent = '已复制!';
        setTimeout(() => { btn.textContent = orig; }, 1500);
      }
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-2xl flex-shrink-0">
              {isImage ? '🖼️' : isPDF ? '📕' : '📄'}
            </span>
            <div className="min-w-0">
              <h3 className="font-semibold text-gray-800 truncate">{file.original_name}</h3>
              <p className="text-xs text-gray-400">
                {formatSize(file.file_size)} · {file.file_type.toUpperCase()}
                {file.version > 1 && ` · v${file.version}`}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 px-4">
          <button
            onClick={() => handleTabSwitch('preview')}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'preview'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            预览
          </button>
          <button
            onClick={() => handleTabSwitch('versions')}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'versions'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            版本历史
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {activeTab === 'preview' ? (
            <div className="h-full">
              {canPreview ? (
                isImage ? (
                  <div className="flex items-center justify-center p-4 min-h-[400px] bg-gray-50">
                    <img
                      src={previewUrl}
                      alt={file.original_name}
                      className="max-w-full max-h-[60vh] object-contain rounded-lg shadow"
                    />
                  </div>
                ) : isPDF ? (
                  <iframe
                    src={previewUrl}
                    className="w-full h-[65vh] border-0"
                    title={file.original_name}
                  />
                ) : isText ? (
                  <TextPreview fileId={file.id} />
                ) : null
              ) : (
                <div className="flex flex-col items-center justify-center min-h-[300px] text-gray-400 space-y-3">
                  <div className="text-5xl">📦</div>
                  <p className="text-sm">此文件类型不支持在线预览</p>
                  <p className="text-xs">请下载后使用本地应用打开</p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-4">
              {loadingVersions ? (
                <div className="text-center py-8 text-gray-400">加载中...</div>
              ) : versions.length > 0 ? (
                <div className="space-y-2">
                  {versions.map((v) => (
                    <div
                      key={v.id}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        v.id === file.id
                          ? 'border-indigo-200 bg-indigo-50'
                          : 'border-gray-100 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-lg">📄</span>
                        <div>
                          <p className="text-sm font-medium text-gray-700">
                            Version {v.version}
                            {v.id === file.id && (
                              <span className="ml-2 text-xs text-indigo-500">(当前)</span>
                            )}
                          </p>
                          <p className="text-xs text-gray-400">
                            {formatSize(v.file_size)} · {formatDate(v.uploaded_at)}
                          </p>
                        </div>
                      </div>
                      <a
                        href={api.getDownloadUrl(v.id)}
                        className="text-xs text-indigo-500 hover:text-indigo-700 font-medium"
                      >
                        下载
                      </a>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-400">
                  <p>暂无版本历史</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center gap-2 p-4 border-t border-gray-100">
          <a
            href={downloadUrl}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            下载
          </a>
          <button
            onClick={handleCopyLink}
            className="flex items-center gap-1.5 px-4 py-2 border border-gray-200 text-gray-600 text-sm rounded-lg hover:bg-gray-50 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684z" />
            </svg>
            复制分享链接
          </button>
        </div>
      </div>
    </div>
  );
}

/** Inline text file preview — fetches content and displays in a pre block */
function TextPreview({ fileId }: { fileId: string }) {
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    fetch(api.getPreviewUrl(fileId), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to load');
        return res.text();
      })
      .then(text => setContent(text))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [fileId]);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">加载中...</div>;
  }
  if (error) {
    return <div className="flex items-center justify-center h-64 text-red-400">{error}</div>;
  }
  return (
    <pre className="p-4 text-sm text-gray-700 font-mono whitespace-pre-wrap break-words max-h-[65vh] overflow-auto">
      {content.slice(0, 50000)}
      {content.length > 50000 && <p className="text-gray-400 mt-2">... 内容已截断 (显示前 50,000 字符)</p>}
    </pre>
  );
}
