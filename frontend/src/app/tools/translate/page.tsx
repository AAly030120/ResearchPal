'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import MultiFileUploader, { UploadedFile } from '@/components/MultiFileUploader';

export default function TranslateToolPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [text, setText] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('zh');
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [resultText, setResultText] = useState('');
  const [taskId, setTaskId] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (uploadedFiles.length === 0 && !text.trim()) { setError('请上传文件或输入文本'); return; }
    setError('');
    setResultText('');
    setTaskId('');
    setProcessing(true);
    try {
      const data: any = { source_lang: sourceLang, target_lang: targetLang };
      if (uploadedFiles.length > 0) {
        data.file_ids = uploadedFiles.map(f => f.id);
        data.file_id = uploadedFiles[0].id;
      }
      if (text.trim()) data.input_text = text;
      const res = await api.post('/api/tasks/translate', data, false, 180000);
      if (res.status === 'failed') {
        setError(res.error_msg || '翻译失败');
      } else if (res.result_text) {
        setResultText(res.result_text);
      }
      if (res.id) setTaskId(res.id);
    } catch (err: any) {
      setError(err.message || 'Translation failed');
    } finally {
      setProcessing(false);
    }
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
        <h1 className="text-2xl font-bold text-gray-900">{t('nav.translate')}</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Language selectors */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">源语言</label>
            <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)} className="w-full p-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none">
              <option value="en">English</option>
              <option value="zh">中文</option>
              <option value="ja">日本語</option>
              <option value="ko">한국어</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
              <option value="es">Español</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">目标语言</label>
            <select value={targetLang} onChange={(e) => setTargetLang(e.target.value)} className="w-full p-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none">
              <option value="zh">中文</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
              <option value="ko">한국어</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
              <option value="es">Español</option>
            </select>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          {/* Multi-file upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">上传需要翻译的文件</label>
            <MultiFileUploader
              onFilesChange={setUploadedFiles}
              accept=".pdf,.docx,.doc,.pptx,.txt,.md,.html,.csv,.xlsx,.json,.py"
            />
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-3 text-gray-400">或直接输入文本翻译</span>
            </div>
          </div>

          {/* Text input */}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="输入需要翻译的文本..."
            className="w-full h-32 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
          />
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
        <div className="mt-6 bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 border-b pb-3 mb-4">翻译结果</h2>
          <div className="prose prose-gray max-w-none text-sm leading-relaxed whitespace-pre-wrap">{resultText}</div>
        </div>
      )}

      {taskId && (
        <div className="mt-6 bg-white rounded-2xl border border-gray-100 p-6 shadow-sm text-center">
          <div className="text-green-600 text-4xl mb-3">&#x2714;</div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">翻译完成！</h2>
          <a
            href={api.getTaskDownloadUrl(taskId)}
            className="inline-flex items-center px-6 py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition-all"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            下载翻译文档
          </a>
        </div>
      )}
    </div>
  );
}
