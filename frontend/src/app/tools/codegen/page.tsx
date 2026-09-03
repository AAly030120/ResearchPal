'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import MultiFileUploader, { UploadedFile } from '@/components/MultiFileUploader';

export default function CodeGenToolPage() {
  const [prompt, setPrompt] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [execute, setExecute] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [resultText, setResultText] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) { setError('请输入代码需求描述'); return; }
    setError('');
    setResultText('');
    setProcessing(true);
    try {
      const data: any = { prompt, execute };
      if (uploadedFiles.length > 0) {
        data.file_ids = uploadedFiles.map(f => f.id);
        data.file_id = uploadedFiles[0].id;
      }
      const res = await api.post('/api/tasks/codegen', data, false, 180000);
      if (res.status === 'failed') {
        setError(res.error_msg || '代码生成失败');
      } else {
        setResultText(res.result_text || 'No result');
      }
    } catch (err: any) {
      setError(err.message || 'Code generation failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(resultText);
  };

  const busy = processing || uploadedFiles.some(f => f.uploading);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center gap-4 mb-8">
        <Link href="/dashboard" className="flex items-center text-gray-500 hover:text-indigo-600 transition-colors text-sm">
          <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t('tools.back')}
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{t('nav.codegen')}</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          {/* Text requirement */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">描述你的代码需求</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="用自然语言描述你需要什么代码，例如：'写一个 Python 函数，读取 CSV 文件并计算每列的均值、中位数和标准差' '生成一个 HTML 页面，包含一个交互式数据表格'"
              className="w-full h-32 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
            />
          </div>

          {/* Multi-file upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">上传参考文件（可选，支持所有格式）</label>
            <MultiFileUploader
              onFilesChange={setUploadedFiles}
              accept=".csv,.xlsx,.xls,.pdf,.docx,.doc,.pptx,.txt,.md,.json,.py,.html,.js,.ts,.jsx,.tsx"
            />
          </div>

          <label className="flex items-center text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={execute} onChange={(e) => setExecute(e.target.checked)} className="mr-2 text-indigo-600 rounded" />
            生成后自动执行 Python 代码
          </label>
        </div>

        {error && <div className="bg-red-50 text-red-600 text-sm p-4 rounded-xl whitespace-pre-wrap">{error}</div>}

        <button type="submit" disabled={busy} className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
          {processing ? t('tools.processing') : t('tools.submit')}
        </button>
      </form>

      {processing && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          <span className="ml-3 text-gray-500">{t('tools.processing')}</span>
        </div>
      )}

      {resultText && (
        <div className="mt-6 bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="px-6 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <h3 className="text-sm font-semibold text-gray-700">{t('tools.result')}</h3>
            <button onClick={handleCopy} className="text-xs px-3 py-1 bg-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-200 transition-colors">
              {t('tools.copy')}
            </button>
          </div>
          <div className="p-6">
            <div className="prose prose-gray max-w-none text-sm whitespace-pre-wrap">{resultText}</div>
          </div>
        </div>
      )}
    </div>
  );
}
