'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';
import MultiFileUploader, { UploadedFile } from '@/components/MultiFileUploader';

const CHART_TYPES = [
  { key: 'bar', label: '柱状图', icon: '📊', desc: '分类对比' },
  { key: 'line', label: '折线图', icon: '📈', desc: '趋势变化' },
  { key: 'pie', label: '饼图', icon: '🥧', desc: '占比分布' },
  { key: 'scatter', label: '散点图', icon: '🔵', desc: '变量关系' },
  { key: 'heatmap', label: '热力图', icon: '🔥', desc: '相关性矩阵' },
  { key: 'box', label: '箱线图', icon: '📦', desc: '分布/离群值' },
];

const STAT_METHODS = [
  { key: 'descriptive', label: '描述性统计', desc: '均值/标准差/分位数' },
  { key: 'correlation', label: '相关性分析', desc: 'Pearson/Spearman' },
  { key: 'ttest', label: 'T 检验', desc: '两组均值比较' },
  { key: 'anova', label: '方差分析', desc: '多组均值比较' },
  { key: 'regression', label: '线性回归', desc: '变量关系建模' },
  { key: 'chi2', label: '卡方检验', desc: '分类变量独立性' },
];

export default function AnalysisToolPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [text, setText] = useState('');
  const [chartTypes, setChartTypes] = useState<string[]>(['bar', 'line']);
  const [statMethods, setStatMethods] = useState<string[]>(['descriptive', 'correlation']);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<any>(null);

  const toggleChart = (key: string) => {
    setChartTypes(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  const toggleStat = (key: string) => {
    setStatMethods(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (uploadedFiles.length === 0) { setError('请上传数据或文档文件'); return; }
    setError('');
    setResult(null);
    setProcessing(true);
    try {
      const data: any = {
        file_ids: uploadedFiles.map(f => f.id),
        file_id: uploadedFiles[0].id,
      };
      if (text.trim()) data.input_text = text;
      data.chart_types = chartTypes;
      data.stat_methods = statMethods;
      const res = await api.post('/api/tasks/analyze', data, false, 180000);
      if (res.status === 'failed') {
        setError(res.error_msg || '数据分析失败');
      } else if (res.result_text) {
        try {
          setResult(JSON.parse(res.result_text));
        } catch {
          setResult({ summary: res.result_text, charts: [], code: '' });
        }
      } else {
        setError('未获取到分析结果');
      }
    } catch (err: any) {
      setError(err.message || 'Analysis failed');
    } finally {
      setProcessing(false);
    }
  };

  const busy = processing || uploadedFiles.some(f => f.uploading);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center gap-4 mb-8">
        <Link href="/dashboard" className="flex items-center text-gray-500 hover:text-indigo-600 transition-colors text-sm">
          <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t('tools.back')}
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{t('nav.analysis')}</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File upload + Text input */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">上传数据/文档文件（支持 CSV、Excel、PDF、Word、PPT、代码等）</label>
            <MultiFileUploader
              onFilesChange={setUploadedFiles}
              accept=".csv,.xlsx,.xls,.pdf,.docx,.doc,.pptx,.txt,.md,.json,.py,.html"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">分析需求（可选）</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="描述你的数据分析需求，例如：'分析各列的统计特征，绘制分布直方图' '计算相关性系数并绘制热力图' '总结文档内容要点'"
              className="w-full h-24 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y text-sm"
            />
          </div>
        </div>

        {/* Chart Type Selector */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">图表类型（可多选）</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {CHART_TYPES.map(ct => (
              <button
                key={ct.key}
                type="button"
                onClick={() => toggleChart(ct.key)}
                className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition-all text-center ${
                  chartTypes.includes(ct.key)
                    ? 'border-indigo-300 bg-indigo-50 text-indigo-700 shadow-sm'
                    : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <span className="text-xl">{ct.icon}</span>
                <span className="text-xs font-medium">{ct.label}</span>
                <span className="text-[10px] opacity-60">{ct.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Statistical Methods */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">统计分析方法（可多选）</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {STAT_METHODS.map(sm => (
              <button
                key={sm.key}
                type="button"
                onClick={() => toggleStat(sm.key)}
                className={`flex items-center gap-2 p-3 rounded-xl border transition-all text-left ${
                  statMethods.includes(sm.key)
                    ? 'border-indigo-300 bg-indigo-50 text-indigo-700 shadow-sm'
                    : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <span className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                  statMethods.includes(sm.key) ? 'border-indigo-600 bg-indigo-600' : 'border-gray-300'
                }`}>
                  {statMethods.includes(sm.key) && (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </span>
                <div>
                  <div className="text-sm font-medium">{sm.label}</div>
                  <div className="text-[10px] opacity-60">{sm.desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {error && <div className="bg-red-50 text-red-600 text-sm p-4 rounded-xl whitespace-pre-wrap">{error}</div>}

        <button type="submit" disabled={busy} className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
          {processing ? t('tools.processing') : '开始分析'}
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
      {result && (
        <div className="mt-6 space-y-6">
          {result.summary && (
            <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 border-b pb-3 mb-4">{t('tools.result')}</h2>
              <div className="prose prose-gray max-w-none text-sm whitespace-pre-wrap">{result.summary}</div>
            </div>
          )}
          {result.charts && result.charts.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-4">图表 ({result.charts.length})</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {result.charts.map((chart: string, i: number) => (
                  <div key={i} className="border border-gray-100 rounded-xl p-4 bg-gray-50">
                    <img src={`data:image/png;base64,${chart}`} alt={`Chart ${i + 1}`} className="w-full rounded-lg" />
                  </div>
                ))}
              </div>
            </div>
          )}
          {result.code && (
            <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3">生成代码</h3>
              <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-sm overflow-x-auto">{result.code}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
