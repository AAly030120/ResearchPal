'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import MultiFileUploader, { UploadedFile } from '@/components/MultiFileUploader';

interface KeywordItem { keyword: string; score: number; }
interface PaperItem { title: string; authors: string[]; doi: string; year: string; journal: string; url: string; }

interface ResultData {
  result_text?: string;
  citations?: Record<string, string>;
  keywords?: KeywordItem[];
  related_papers?: PaperItem[];
}

const CITATION_STYLES = [
  { value: '', label: '自动 (全部格式)' },
  { value: 'apa', label: 'APA 7th' },
  { value: 'mla', label: 'MLA 9th' },
  { value: 'chicago', label: 'Chicago 17th' },
  { value: 'gbt7714', label: 'GB/T 7714' },
];

const tabOptions = [
  { key: 'summary', label: '文献总结' },
  { key: 'citation', label: '引用格式' },
  { key: 'keywords', label: '关键词' },
  { key: 'related', label: '相似文献' },
] as const;

type TabKey = typeof tabOptions[number]['key'];

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {}).catch(() => {});
}

export default function SummaryToolPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [text, setText] = useState('');
  const [citationStyle, setCitationStyle] = useState('');
  const [outputLanguage, setOutputLanguage] = useState('auto');
  const [extractKeywords, setExtractKeywords] = useState(true);
  const [recommendRelated, setRecommendRelated] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ResultData>({});
  const [activeTab, setActiveTab] = useState<TabKey>('summary');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (uploadedFiles.length === 0 && !text.trim()) { setError('请上传文件或输入文本'); return; }
    setError('');
    setResult({});
    setProcessing(true);
    try {
      const data: any = {};
      if (uploadedFiles.length > 0) {
        data.file_ids = uploadedFiles.map(f => f.id);
        data.file_id = uploadedFiles[0].id;
      }
      if (text.trim()) data.input_text = text;
      if (citationStyle) data.citation_style = citationStyle;
      data.output_language = outputLanguage;
      data.extract_keywords = extractKeywords;
      data.recommend_related = recommendRelated;

      const res = await api.post('/api/tasks/summarize', data, false, 180000);
      if (res.status === 'failed') {
        setError(res.error_msg || '文献总结失败');
      } else {
        const hasKeywords = res.keywords && res.keywords.length > 0;
        const hasRelated = res.related_papers && res.related_papers.length > 0;
        setResult({
          result_text: res.result_text || 'No result returned',
          citations: res.citations || undefined,
          keywords: res.keywords || undefined,
          related_papers: res.related_papers || undefined,
        });

        // Auto-switch to a meaningful tab
        if (res.result_text) setActiveTab('summary');
        else if (hasKeywords) setActiveTab('keywords');
        else if (hasRelated) setActiveTab('related');
      }
    } catch (err: any) {
      setError(err.message || 'Processing failed');
    } finally {
      setProcessing(false);
    }
  };

  const hasResult = result.result_text || (result.keywords && result.keywords.length > 0);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center gap-4 mb-8">
        <Link href="/dashboard" className="flex items-center text-gray-500 hover:text-indigo-600 transition-colors text-sm">
          <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t('tools.back')}
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{t('nav.summary')}</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Upload + Text Input */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">上传文献文件（支持 PDF、Word、PPT、TXT 等）</label>
            <MultiFileUploader
              onFilesChange={setUploadedFiles}
              accept=".pdf,.docx,.doc,.pptx,.txt,.md,.csv,.xlsx,.json,.py,.html"
            />
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-white px-3 text-gray-400">并/或直接输入文本</span></div>
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="粘贴论文、报告或任意文本内容..."
            className="w-full h-36 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
          />
        </div>

        {/* Advanced Options */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">高级选项</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Output Language */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">输出语言</label>
              <select
                value={outputLanguage}
                onChange={(e) => setOutputLanguage(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
              >
                <option value="auto">自动 (与原文一致)</option>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>

            {/* Citation Style */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">引用格式</label>
              <select
                value={citationStyle}
                onChange={(e) => setCitationStyle(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
              >
                {CITATION_STYLES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* Keyword Toggle */}
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={extractKeywords}
                  onChange={(e) => setExtractKeywords(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-600">提取关键词 (TF-IDF)</span>
              </label>
            </div>

            {/* Related Paper Toggle */}
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={recommendRelated}
                  onChange={(e) => setRecommendRelated(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-600">推荐相似文献 (Crossref)</span>
              </label>
            </div>
          </div>
        </div>

        {error && <div className="bg-red-50 text-red-600 text-sm p-4 rounded-xl whitespace-pre-wrap">{error}</div>}

        <button
          type="submit"
          disabled={processing || (uploadedFiles.some(f => f.uploading))}
          className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {processing ? t('tools.processing') : t('tools.submit')}
        </button>
      </form>

      {/* Processing */}
      {processing && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          <span className="ml-3 text-gray-500">{t('tools.processing')}</span>
        </div>
      )}

      {/* Results */}
      {hasResult && (
        <div className="mt-6 bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          {/* Tab Bar */}
          <div className="flex border-b border-gray-100 bg-gray-50 px-4">
            {tabOptions.map(tab => {
              let show = false;
              if (tab.key === 'summary') show = !!result.result_text;
              if (tab.key === 'citation') show = result.citations && Object.keys(result.citations).length > 0;
              if (tab.key === 'keywords') show = result.keywords && result.keywords.length > 0;
              if (tab.key === 'related') show = result.related_papers && result.related_papers.length > 0;
              if (!show) return null;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-all -mb-px ${activeTab === tab.key ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* Summary Tab */}
            {activeTab === 'summary' && result.result_text && (
              <div className="prose prose-gray max-w-none text-sm leading-relaxed whitespace-pre-wrap">{result.result_text}</div>
            )}

            {/* Citation Tab */}
            {activeTab === 'citation' && result.citations && (
              <div className="space-y-4">
                <p className="text-xs text-gray-400">自动从文献中提取元数据生成引用格式，点击右上角按钮复制</p>
                {Object.entries(result.citations).map(([style, text]) => (
                  <div key={style} className="bg-gray-50 rounded-xl p-4 relative group">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-indigo-600 uppercase">{style === 'gbt7714' ? 'GB/T 7714' : style.toUpperCase()}</span>
                      <button
                        onClick={() => copyToClipboard(text)}
                        className="text-xs text-gray-400 hover:text-indigo-600 transition-colors opacity-0 group-hover:opacity-100"
                      >
                        📋 复制
                      </button>
                    </div>
                    <p className="text-sm text-gray-800 leading-relaxed">{text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Keywords Tab */}
            {activeTab === 'keywords' && result.keywords && (
              <div>
                <p className="text-xs text-gray-400 mb-4">TF-IDF 算法提取的关键词，按相关性排序</p>
                <div className="flex flex-wrap gap-2">
                  {result.keywords.map((kw, i) => {
                    // Scale font size and opacity based on score
                    const maxScore = result.keywords![0]?.score || 1;
                    const ratio = kw.score / maxScore;
                    const size = ratio > 0.7 ? 'text-base px-4 py-2' : ratio > 0.4 ? 'text-sm px-3 py-1.5' : 'text-xs px-2 py-1';
                    return (
                      <span key={i} className={`inline-flex items-center gap-1.5 bg-indigo-50 text-indigo-700 rounded-full font-medium ${size} transition-all hover:bg-indigo-100`}>
                        {kw.keyword}
                        <span className="text-indigo-300">{Math.round(kw.score * 100)}</span>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Related Papers Tab */}
            {activeTab === 'related' && result.related_papers && (
              <div className="space-y-3">
                <p className="text-xs text-gray-400 mb-4">通过 Crossref API 检索的相似文献推荐</p>
                {result.related_papers.map((paper, i) => (
                  <div key={i} className="bg-gray-50 rounded-xl p-4 hover:bg-gray-100 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-gray-900 mb-1 line-clamp-2">
                          {paper.url ? (
                            <a href={paper.url} target="_blank" rel="noopener noreferrer" className="hover:text-indigo-600 transition-colors">
                              {paper.title}
                            </a>
                          ) : paper.title}
                        </h4>
                        {paper.authors.length > 0 && (
                          <p className="text-xs text-gray-500 mb-1">{paper.authors.join(', ')}</p>
                        )}
                        <div className="flex items-center gap-3 text-xs text-gray-400">
                          {paper.journal && <span>📖 {paper.journal}</span>}
                          {paper.year && <span>📅 {paper.year}</span>}
                          {paper.doi && <span className="font-mono text-[10px]">DOI: {paper.doi}</span>}
                        </div>
                      </div>
                      {paper.doi && (
                        <button
                          onClick={() => copyToClipboard(paper.doi)}
                          className="text-xs text-gray-400 hover:text-indigo-600 transition-colors flex-shrink-0"
                          title="复制 DOI"
                        >
                          📋
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
