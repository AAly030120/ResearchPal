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
  }, [user]);

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
