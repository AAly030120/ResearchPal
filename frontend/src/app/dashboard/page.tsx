'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import FileUploader from '@/components/FileUploader';
import FilePreviewModal from '@/components/FilePreviewModal';

interface FileItem {
  id: string;
  filename: string;
  original_name: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  version: number;
  version_group?: string;
  indexed?: boolean;
  chunks_count?: number;
}

interface TaskItem {
  id: string;
  task_type: string;
  status: string;
  result_path: string | null;
  result_text: string | null;
  error_msg: string | null;
  created_at: string;
}

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  done: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

const typeIcons: Record<string, string> = {
  pdf: '\u{1F4D5}',
  docx: '\u{1F4DD}',
  doc: '\u{1F4DD}',
  xlsx: '\u{1F4CA}',
  xls: '\u{1F4CA}',
  csv: '\u{1F4CA}',
  py: '\u{1F40D}',
  html: '\u{1F310}',
  json: '\u{1F4CB}',
  txt: '\u{1F4C4}',
  md: '\u{1F4DD}',
  pptx: '\u{1F4CA}',
  png: '\u{1F5BC}',
  jpg: '\u{1F5BC}',
  jpeg: '\u{1F5BC}',
  gif: '\u{1F5BC}',
  svg: '\u{1F5BC}',
};

function formatSize(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

const taskTypeNames: Record<string, string> = {
  summarize: 'Summarize',
  ppt: 'PPT',
  analysis: 'Analysis',
  codegen: 'Code Gen',
  translate: 'Translate',
};

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'files' | 'tasks'>('files');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [ragStatus, setRagStatus] = useState<{ provider?: string; total_indexed_chunks?: number; indexed_files?: number } | null>(null);
  const [indexingAll, setIndexingAll] = useState(false);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [kgStatus, setKgStatus] = useState<{
    stats?: { entities: number; triples: number; communities: number };
    files?: Array<{ id: string; name: string; type: string; indexed: boolean; kg_entities: number; kg_ready: boolean }>;
  } | null>(null);
  const [kgIndexingAll, setKgIndexingAll] = useState(false);
  const [kgIndexingId, setKgIndexingId] = useState<string | null>(null);
  const [kgCommunitiesLoading, setKgCommunitiesLoading] = useState(false);

  // File types that can be embedded & retrieved via RAG / GraphRAG.
  const INDEXABLE = new Set(['pdf', 'docx', 'txt', 'md', 'pptx']);

  const loadRagStatus = useCallback(async () => {
    if (!user) return;
    try {
      const data = await api.get('/api/rag/status');
      setRagStatus({
        provider: data.provider,
        total_indexed_chunks: data.total_indexed_chunks,
        indexed_files: data.indexed_files,
      });
    } catch {
      /* RAG status is best-effort */
    }
  }, [user]);

  const loadKgStatus = useCallback(async () => {
    if (!user) return;
    try {
      const data = await api.get('/api/kg/status');
      setKgStatus({
        stats: data.stats || { entities: 0, triples: 0, communities: 0 },
        files: data.files || [],
      });
    } catch {
      /* KG status is best-effort */
    }
  }, [user]);

  const kgFileInfo = (fileId: string) => kgStatus?.files?.find((f) => f.id === fileId);

  const handleKgIndexOne = async (fileId: string) => {
    setKgIndexingId(fileId);
    try {
      await api.post(`/api/kg/index/${fileId}`, {});
      await loadKgStatus();
    } catch (err: any) {
      setError(err.message || '构建图谱失败');
    } finally {
      setKgIndexingId(null);
    }
  };

  const handleKgIndexAll = async () => {
    setKgIndexingAll(true);
    try {
      await api.post('/api/kg/index-all', {});
      await loadKgStatus();
    } catch (err: any) {
      setError(err.message || '构建图谱失败');
    } finally {
      setKgIndexingAll(false);
    }
  };

  const handleKgCommunities = async () => {
    setKgCommunitiesLoading(true);
    try {
      await api.post('/api/kg/communities', {});
      await loadKgStatus();
    } catch (err: any) {
      setError(err.message || '社区检测失败');
    } finally {
      setKgCommunitiesLoading(false);
    }
  };



  const loadData = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    const errors: string[] = [];
    await api.get('/api/files/')
      .then((data: any) => setFiles(Array.isArray(data) ? data : []))
      .catch((err: any) => errors.push(`文件列表: ${err.message}`));
    await api.get('/api/tasks/')
      .then((data: any) => setTasks(Array.isArray(data) ? data : []))
      .catch((err: any) => errors.push(`任务列表: ${err.message}`));
    if (errors.length > 0) setError(errors.join('; '));
    setLoading(false);
    loadRagStatus();
    loadKgStatus();
  }, [user, loadRagStatus, loadKgStatus]);

  const handleReindex = async (fileId: string) => {
    setReindexingId(fileId);
    try {
      await api.post(`/api/rag/index/${fileId}`, {});
      await loadData();
    } catch (err: any) {
      setError(err.message || '索引失败');
    } finally {
      setReindexingId(null);
    }
  };

  const handleIndexAll = async () => {
    setIndexingAll(true);
    try {
      await api.post('/api/rag/index-all', {});
      await loadData();
    } catch (err: any) {
      setError(err.message || '索引失败');
    } finally {
      setIndexingAll(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
      return;
    }
    if (user) loadData();
  }, [user, authLoading, loadData, router]);

  const handleDeleteFile = async (fileId: string) => {
    try {
      await api.delete(`/api/files/${fileId}`);
      setFiles(files.filter((f) => f.id !== fileId));
    } catch (err: any) {
      setError(err.message || 'Failed to delete file');
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await api.delete(`/api/tasks/${taskId}`);
      setTasks(tasks.filter((t) => t.id !== taskId));
    } catch (err: any) {
      setError(err.message || 'Failed to delete task');
    }
  };

  const handleCopyShareLink = (fileId: string) => {
    const link = `${window.location.origin}/api/files/download/${fileId}`;
    navigator.clipboard.writeText(link).then(() => {
      setCopiedId(fileId);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  if (authLoading) {
    return <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]"><div className="text-gray-500">{t('common.loading')}</div></div>;
  }
  if (!user) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{t('nav.dashboard')}</h1>
          <p className="text-gray-500 mt-1">Welcome back, {user.username}</p>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
        {[
          { label: t('nav.summary'), href: '/tools/summary', icon: '\u{1F4D6}', color: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100' },
          { label: t('nav.ppt'), href: '/tools/ppt', icon: '\u{1F4CA}', color: 'bg-purple-50 text-purple-700 hover:bg-purple-100' },
          { label: t('nav.analysis'), href: '/tools/analysis', icon: '\u{1F4C8}', color: 'bg-green-50 text-green-700 hover:bg-green-100' },
          { label: t('nav.codegen'), href: '/tools/codegen', icon: '\u{1F4BB}', color: 'bg-orange-50 text-orange-700 hover:bg-orange-100' },
          { label: t('nav.translate'), href: '/tools/translate', icon: '\u{1F30D}', color: 'bg-teal-50 text-teal-700 hover:bg-teal-100' },
        ].map((action) => (
          <Link key={action.href} href={action.href} className={`flex flex-col items-center justify-center p-4 rounded-xl transition-all text-center ${action.color}`}>
            <span className="text-2xl mb-1">{action.icon}</span>
            <span className="text-sm font-medium">{action.label}</span>
          </Link>
        ))}
      </div>

      <div className="mb-8"><FileUploader onUpload={() => loadData()} /></div>

      <div className="flex space-x-1 bg-gray-100 rounded-lg p-1 mb-6 w-fit">
        <button onClick={() => setActiveTab('files')} className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${activeTab === 'files' ? 'bg-white shadow text-indigo-600' : 'text-gray-600 hover:text-gray-900'}`}>{t('dashboard.files')}</button>
        <button onClick={() => setActiveTab('tasks')} className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${activeTab === 'tasks' ? 'bg-white shadow text-indigo-600' : 'text-gray-600 hover:text-gray-900'}`}>{t('dashboard.tasks')}</button>
      </div>

      {error && <div className="bg-red-50 text-red-600 text-sm p-4 rounded-xl mb-6">{error} <button onClick={loadData} className="ml-2 underline">{t('common.retry')}</button></div>}

      {activeTab === 'files' && (
        <div className="flex items-center justify-between mb-4 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
          <div className="text-sm text-emerald-800">
            <span className="font-medium">检索增强 (RAG)：</span>
            {ragStatus
              ? `已索引 ${ragStatus.indexed_files ?? 0} 个文件 / ${ragStatus.total_indexed_chunks ?? 0} 个片段（向量模型：${ragStatus.provider}）`
              : '加载中…'}
            <span className="text-emerald-600 ml-1">支持 PDF / DOCX / TXT / MD / PPTX</span>
          </div>
          <button
            onClick={handleIndexAll}
            disabled={indexingAll}
            className="px-3 py-1.5 text-xs font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {indexingAll ? '索引中…' : '重新索引全部'}
          </button>
        </div>
      )}

      {activeTab === 'files' && (
        <div className="flex items-center justify-between mb-4 bg-sky-50 border border-sky-200 rounded-xl px-4 py-3">
          <div className="text-sm text-sky-800">
            <span className="font-medium">知识图谱 (GraphRAG)：</span>
            {kgStatus
              ? `已抽取 ${kgStatus.stats?.entities ?? 0} 个实体 / ${kgStatus.stats?.triples ?? 0} 条关系 / ${kgStatus.stats?.communities ?? 0} 个社区`
              : '加载中…'}
            <span className="text-sky-600 ml-1">基于实体关系多跳检索增强回答</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleKgCommunities}
              disabled={kgCommunitiesLoading || kgIndexingAll}
              className="px-3 py-1.5 text-xs font-medium text-white bg-sky-500 rounded-lg hover:bg-sky-600 disabled:opacity-50 transition-colors"
              title="社区发现+LLM摘要（全局主题视图）"
            >
              {kgCommunitiesLoading ? '检测中…' : '检测社区'}
            </button>
            <button
              onClick={handleKgIndexAll}
              disabled={kgIndexingAll}
              className="px-3 py-1.5 text-xs font-medium text-white bg-sky-600 rounded-lg hover:bg-sky-700 disabled:opacity-50 transition-colors"
            >
              {kgIndexingAll ? '构建中…' : '重建全部图谱'}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-20 text-gray-500">{t('common.loading')}</div>
      ) : activeTab === 'files' ? (
        files.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-2xl border border-gray-100"><div className="text-4xl mb-3">&#x1F4C2;</div><p className="text-gray-500">{t('dashboard.noFiles')}</p></div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {files.map((file) => (
              <div key={file.id} className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-shadow">
                {/* Header: icon + version badge + delete */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{typeIcons[file.file_type] || '\u{1F4C4}'}</span>
                    {file.version > 1 && (
                      <span className="text-[10px] bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded font-medium">
                        v{file.version}
                      </span>
                    )}
                    {INDEXABLE.has(file.file_type) && (
                      file.indexed ? (
                        <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-medium flex items-center gap-0.5">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0L3.3 9.7a1 1 0 011.4-1.4l3.1 3.1 6.8-6.8a1 1 0 011.4 0z" clipRule="evenodd" /></svg>
                          已索引{file.chunks_count ? ` · ${file.chunks_count}` : ''}
                        </span>
                      ) : (
                        <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-medium">未索引</span>
                      )
                    )}
                    {INDEXABLE.has(file.file_type) && kgFileInfo(file.id)?.kg_ready && (
                      <span className="text-[10px] bg-sky-100 text-sky-700 px-1.5 py-0.5 rounded font-medium flex items-center gap-0.5">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 5a2 2 0 11-4 0 2 2 0 014 0zM21 7a2 2 0 11-4 0 2 2 0 014 0zM12 21a2 2 0 11-4 0 2 2 0 014 0zM4.5 5.5l5.5 13M17 7l-4.5 12.5M19 7l-13 1.5" /></svg>
                        图谱已建
                      </span>
                    )}
                  </div>
                  <button onClick={() => handleDeleteFile(file.id)} className="text-gray-400 hover:text-red-500 transition-colors" title="Delete">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>

                {/* File name */}
                <h3 className="font-medium text-gray-900 text-sm truncate mb-2" title={file.original_name}>
                  {file.original_name || file.filename}
                </h3>

                {/* Size & Date */}
                <div className="flex items-center justify-between text-xs text-gray-400 mb-3">
                  <span>{formatSize(file.file_size)}</span>
                  <span>{new Date(file.uploaded_at).toLocaleDateString()}</span>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-1.5 pt-2 border-t border-gray-50">
                  {/* Preview */}
                  <button
                    onClick={() => setPreviewFile(file)}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-indigo-50 hover:text-indigo-600 transition-colors"
                    title="预览"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    预览
                  </button>

                  {/* Download */}
                  <a
                    href={api.getDownloadUrl(file.id)}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-green-50 hover:text-green-600 transition-colors"
                    title="下载"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    下载
                  </a>

                  {/* Share */}
                  <button
                    onClick={() => handleCopyShareLink(file.id)}
                    className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                      copiedId === file.id
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-50 text-gray-600 hover:bg-blue-50 hover:text-blue-600'
                    }`}
                    title="复制分享链接"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684z" />
                    </svg>
                    {copiedId === file.id ? '已复制' : '分享'}
                  </button>

                  {/* Re-index (RAG) */}
                  {INDEXABLE.has(file.file_type) && (
                    <button
                      onClick={() => handleReindex(file.id)}
                      disabled={reindexingId === file.id}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-emerald-50 hover:text-emerald-600 transition-colors disabled:opacity-50"
                      title={file.indexed ? '重新建立索引' : '建立索引以启用检索增强'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0114.5-3.5L20 8M20 15a9 9 0 01-14.5 3.5L4 16" />
                      </svg>
                      {reindexingId === file.id ? '索引中' : (file.indexed ? '重索引' : '索引')}
                    </button>
                  )}

                  {/* Build knowledge graph (GraphRAG) */}
                  {INDEXABLE.has(file.file_type) && (
                    <button
                      onClick={() => handleKgIndexOne(file.id)}
                      disabled={kgIndexingId === file.id}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-sky-50 hover:text-sky-600 transition-colors disabled:opacity-50"
                      title={kgFileInfo(file.id)?.kg_ready ? '更新知识图谱' : '抽取实体与关系，构建知识图谱'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 11-4 0 2 2 0 014 0zM21 7a2 2 0 11-4 0 2 2 0 014 0zM12 21a2 2 0 11-4 0 2 2 0 014 0zM4.5 5.5l5.5 13M17 7l-4.5 12.5M19 7l-13 1.5" />
                      </svg>
                      {kgIndexingId === file.id ? '建图中' : (kgFileInfo(file.id)?.kg_ready ? '更新图' : '建图')}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        tasks.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-2xl border border-gray-100"><div className="text-4xl mb-3">&#x1F4CB;</div><p className="text-gray-500">{t('dashboard.noTasks')}</p></div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {tasks.map((task) => (
                  <tr key={task.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{taskTypeNames[task.task_type] || task.task_type}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full ${statusColors[task.status] || 'bg-gray-100 text-gray-800'}`}>
                        {t(`status.${task.status}`)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">{new Date(task.created_at).toLocaleString()}</td>
                    <td className="px-6 py-4 flex gap-2">
                      {task.status === 'done' && task.result_path && (
                        <a
                          href={api.getTaskDownloadUrl(task.id)}
                          className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                        >
                          {t('tools.download')}
                        </a>
                      )}
                      <button onClick={() => handleDeleteTask(task.id)} className="text-sm text-red-400 hover:text-red-600">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Preview Modal */}
      {previewFile && (
        <FilePreviewModal
          file={{
            id: previewFile.id,
            original_name: previewFile.original_name,
            file_type: previewFile.file_type,
            file_size: previewFile.file_size,
            version: previewFile.version || 1,
          }}
          onClose={() => setPreviewFile(null)}
        />
      )}
    </div>
  );
}
