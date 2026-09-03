'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import MultiFileUploader, { UploadedFile } from '@/components/MultiFileUploader';

const LANGUAGE_OPTIONS = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
];

export default function PPTToolPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [text, setText] = useState('');
  const [styleDescription, setStyleDescription] = useState('');
  const [language, setLanguage] = useState('zh');
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [taskId, setTaskId] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (uploadedFiles.length === 0 && !text.trim()) { setError('请上传参考文档或输入 PPT 内容'); return; }
    setError('');
    setTaskId('');
    setProcessing(true);
    try {
      const data: any = { language };
      if (uploadedFiles.length > 0) {
        data.file_ids = uploadedFiles.map(f => f.id);
        data.file_id = uploadedFiles[0].id;
      }
      if (text.trim()) data.text = text;
      if (styleDescription.trim()) data.style_description = styleDescription;
      const res = await api.post('/api/tasks/ppt', data, false, 180000);
      if (res.status === 'failed') {
        setError(res.error_msg || 'PPT 生成失败');
      } else if (res.id) {
        setTaskId(res.id);
      }
    } catch (err: any) {
      setError(err.message || 'PPT generation failed');
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
        <h1 className="text-2xl font-bold text-gray-900">{t('nav.ppt')}</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          {/* File upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">上传参考文档（PDF、Word、PPT、TXT 等）</label>
            <MultiFileUploader
              onFilesChange={setUploadedFiles}
              accept=".pdf,.docx,.doc,.pptx,.txt,.md,.csv,.xlsx,.json,.py,.html"
            />
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-3 text-gray-400">并/或输入 PPT 内容描述</span>
            </div>
          </div>

          {/* Text input */}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="描述你需要制作的 PPT 主题和内容，例如：'制作一份关于机器学习基础概念的培训PPT，包括：1.什么是机器学习 2.监督学习 3.常见算法 4.应用案例'"
            className="w-full h-32 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
          />
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              描述你想要的 PPT 风格（自然语言描述，越详细越好）
            </label>
            <textarea
              value={styleDescription}
              onChange={(e) => setStyleDescription(e.target.value)}
              placeholder="例如：深蓝色科技风，大标题，圆角卡片布局，使用 Montserrat 字体，大量留白。或：学术答辩风格，白色背景，左侧红色强调条，宋体标题，图表用蓝色系。"
              className="w-full h-24 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
            />
            <p className="text-xs text-gray-400 mt-1.5">若不填写则自动匹配最佳风格</p>
          </div>

          <div className="w-48">
            <label className="block text-sm font-medium text-gray-700 mb-2">输出语言</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className="w-full p-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm">
              {LANGUAGE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="bg-blue-50 text-blue-700 text-sm p-4 rounded-xl whitespace-pre-wrap">{error}</div>}

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

      {taskId && (
        <div className="mt-6 bg-white rounded-2xl border border-gray-100 p-6 shadow-sm text-center">
          <div className="text-green-600 text-4xl mb-3">&#x2714;</div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">PPT 生成完毕！</h2>
          <a
            href={api.getTaskDownloadUrl(taskId)}
            className="inline-flex items-center px-6 py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition-all"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            下载 PPT 文件
          </a>
        </div>
      )}
    </div>
  );
}
