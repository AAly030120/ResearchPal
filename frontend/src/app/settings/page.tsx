'use client';
import { useState, useEffect, FormEvent, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { t, getLanguage, setLanguage } from '@/lib/i18n';
import { api } from '@/lib/api';

interface KeyStatus {
  key_env: string;
  configured: boolean;
  masked: string;
  label: string;
}

interface ModelInfo {
  key: string;
  name: string;
  provider: string;
  available: boolean;
  key_env: string;
}

export default function SettingsPage() {
  const { user, loading: authLoading, updateUser } = useAuth();
  const router = useRouter();
  const [model, setModel] = useState('gpt-4o');
  const [lang, setLang] = useState(getLanguage());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // API Key state
  const [keyStatuses, setKeyStatuses] = useState<KeyStatus[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [demoMode, setDemoMode] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [keySaving, setKeySaving] = useState(false);
  const [keyMessage, setKeyMessage] = useState('');
  const [loadingKeys, setLoadingKeys] = useState(true);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
      return;
    }
    if (user) {
      setModel(user.preferred_model || 'gpt-4o');
      setLang(user.language || getLanguage());
      loadKeyStatus();
      loadModels();
    }
  }, [user, authLoading]);

  const loadKeyStatus = async () => {
    try {
      const data = await api.getApiKeyStatus();
      setKeyStatuses(data);
    } catch { /* ignore */ }
    setLoadingKeys(false);
  };

  const loadModels = async () => {
    try {
      const data = await api.getModelsStatus();
      setModels(data.models || []);
      setDemoMode(data.demo_mode);
    } catch { /* ignore */ }
  };

  const handleSaveKey = useCallback(async (keyEnv: string) => {
    setKeySaving(true);
    setKeyMessage('');
    try {
      await api.setApiKey(keyEnv, keyInput);
      setKeyMessage(`${keyEnv} 配置成功！`);
      setEditingKey(null);
      setKeyInput('');
      loadKeyStatus();
      loadModels();
      setTimeout(() => setKeyMessage(''), 3000);
    } catch (err: any) {
      setKeyMessage(`配置失败: ${err.message}`);
    } finally {
      setKeySaving(false);
    }
  }, [keyInput]);

  const handleDeleteKey = useCallback(async (keyEnv: string) => {
    if (!confirm(`确定要删除 ${keyEnv} 吗？`)) return;
    try {
      await api.deleteApiKey(keyEnv);
      loadKeyStatus();
      loadModels();
      setKeyMessage('API Key 已删除');
      setTimeout(() => setKeyMessage(''), 3000);
    } catch (err: any) {
      setKeyMessage(`删除失败: ${err.message}`);
    }
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);

    try {
      await updateUser({ preferred_model: model, language: lang });
      setLanguage(lang);
      setSuccess('Settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  // Helper to check if a model's provider key is configured
  const isModelKeyConfigured = (modelKey: string) => {
    const m = models.find((x) => x.key === modelKey);
    return m ? m.available : false;
  };

  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="text-gray-500">{t('common.loading')}</div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex items-center gap-4">
        <Link
          href="/dashboard"
          className="flex items-center text-gray-500 hover:text-indigo-600 transition-colors text-sm"
        >
          <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t('tools.back')}
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{t('settings.title')}</h1>
      </div>

      {/* Demo Mode Banner */}
      {demoMode && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <span className="text-2xl flex-shrink-0">&#x26A0;&#xFE0F;</span>
          <div>
            <h3 className="font-semibold text-amber-800 text-sm">Demo 模式</h3>
            <p className="text-amber-700 text-sm mt-1">
              尚未配置任何 AI 模型的 API Key。请在下方配置至少一个 Key 以启用 AI 功能。
            </p>
          </div>
        </div>
      )}

      {!demoMode && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-start gap-3">
          <span className="text-2xl flex-shrink-0">&#x2705;</span>
          <div>
            <h3 className="font-semibold text-green-800 text-sm">AI 功能已就绪</h3>
            <p className="text-green-700 text-sm mt-1">
              已配置 API Key，所有 AI 工具均可正常使用。
            </p>
          </div>
        </div>
      )}

      {/* API Keys Section */}
      <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-gray-800 mb-1">&#x1F511; AI 模型 API Key 配置</h2>
        <p className="text-sm text-gray-500 mb-6">
          配置后即可让文献总结、PPT制作、数据分析等功能接入真实 AI 大模型。Key 仅保存在本地服务器，不会上传。
        </p>

        {loadingKeys ? (
          <div className="text-sm text-gray-400 py-4">{t('common.loading')}</div>
        ) : (
          <div className="space-y-4">
            {keyStatuses.map((ks) => (
              <div key={ks.key_env} className="border border-gray-200 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h4 className="font-medium text-sm text-gray-800">{ks.label}</h4>
                    <p className="text-xs text-gray-400">
                      {ks.configured
                        ? `已配置: ${ks.masked}`
                        : '未配置'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {ks.configured && (
                      <span className="inline-flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        已配置
                      </span>
                    )}
                  </div>
                </div>

                {editingKey === ks.key_env ? (
                  <div className="flex gap-2 mt-2">
                    <input
                      type="password"
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={`输入 ${ks.label} 的 API Key...`}
                      className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveKey(ks.key_env)}
                      disabled={!keyInput.trim() || keySaving}
                      className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      {keySaving ? '...' : '保存'}
                    </button>
                    <button
                      onClick={() => { setEditingKey(null); setKeyInput(''); }}
                      className="px-3 py-2 text-gray-500 text-sm hover:text-gray-700"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => { setEditingKey(ks.key_env); setKeyInput(''); }}
                      className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                    >
                      {ks.configured ? '更换 Key' : '配置 Key'}
                    </button>
                    {ks.configured && (
                      <button
                        onClick={() => handleDeleteKey(ks.key_env)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        删除
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {keyMessage && (
          <div className={`mt-4 text-sm p-3 rounded-lg ${
            keyMessage.includes('失败') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'
          }`}>
            {keyMessage}
          </div>
        )}

        {/* API Key获取指引 */}
        <div className="mt-6 bg-gray-50 rounded-xl p-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">如何获取 API Key？</h4>
          <ul className="text-xs text-gray-500 space-y-1.5">
            <li>&#x1F4CC; <strong>OpenAI:</strong> 访问 <a href="https://platform.openai.com/api-keys" target="_blank" className="text-indigo-600 underline">platform.openai.com/api-keys</a></li>
            <li>&#x1F4CC; <strong>DeepSeek:</strong> 访问 <a href="https://platform.deepseek.com/api_keys" target="_blank" className="text-indigo-600 underline">platform.deepseek.com/api_keys</a>（注册即送额度）</li>
            <li>&#x1F4CC; <strong>智谱 GLM:</strong> 访问 <a href="https://open.bigmodel.cn/usercenter/apikeys" target="_blank" className="text-indigo-600 underline">open.bigmodel.cn</a></li>
            <li>&#x1F4CC; <strong>通义千问:</strong> 访问 <a href="https://bailian.console.aliyun.com/" target="_blank" className="text-indigo-600 underline">bailian.console.aliyun.com</a>（开通 DashScope）</li>
          </ul>
        </div>
      </div>

      {/* Model Selection */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <label className="block text-sm font-semibold text-gray-700 mb-3">
            {t('settings.model')}
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm"
          >
            <option value="gpt-4o">
              GPT-4o {!isModelKeyConfigured('gpt-4o') ? '(需要配置 OpenAI Key)' : ''}
            </option>
            <option value="gpt-4o-mini">
              GPT-4o Mini {!isModelKeyConfigured('gpt-4o-mini') ? '(需要配置 OpenAI Key)' : ''}
            </option>
            <option value="deepseek-chat">
              DeepSeek V3 {!isModelKeyConfigured('deepseek-chat') ? '(需要配置 DeepSeek Key)' : ''}
            </option>
            <option value="deepseek-v4-flash">
              DeepSeek V4 Flash {!isModelKeyConfigured('deepseek-v4-flash') ? '(需要配置 DeepSeek Key)' : ''}
            </option>
            <option value="glm-4-flash">
              智谱 GLM-4 Flash {!isModelKeyConfigured('glm-4-flash') ? '(需要配置 GLM Key)' : ''}
            </option>
            <option value="glm-5.2">
              智谱 GLM-5.2 {!isModelKeyConfigured('glm-5.2') ? '(需要配置 GLM Key)' : ''}
            </option>
            <option value="qwen3.5-397b-a17b">
              通义千问 Qwen3.5-397B {!isModelKeyConfigured('qwen3.5-397b-a17b') ? '(需要配置 Qwen Key)' : ''}
            </option>
            <option value="qwen3.5-27b">
              通义千问 Qwen3.5-27B {!isModelKeyConfigured('qwen3.5-27b') ? '(需要配置 Qwen Key)' : ''}
            </option>
          </select>
          <p className="text-xs text-gray-400 mt-2">选择默认的 AI 模型，工具调用时将使用此模型</p>
        </div>

        {/* Language Toggle */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <label className="block text-sm font-semibold text-gray-700 mb-3">
            {t('settings.language')}
          </label>
          <div className="flex space-x-1 bg-gray-100 rounded-lg p-1 w-fit">
            <button
              type="button"
              onClick={() => setLang('zh')}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                lang === 'zh' ? 'bg-white shadow text-indigo-600' : 'text-gray-600'
              }`}
            >
              中文
            </button>
            <button
              type="button"
              onClick={() => setLang('en')}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                lang === 'en' ? 'bg-white shadow text-indigo-600' : 'text-gray-600'
              }`}
            >
              English
            </button>
          </div>
        </div>

        {/* Status Messages */}
        {error && (
          <div className="bg-red-50 text-red-600 text-sm p-4 rounded-xl">{error}</div>
        )}
        {success && (
          <div className="bg-green-50 text-green-600 text-sm p-4 rounded-xl">{success}</div>
        )}

        {/* Save Button */}
        <button
          type="submit"
          disabled={saving}
          className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {saving ? t('common.loading') : t('settings.save')}
        </button>
      </form>
    </div>
  );
}
