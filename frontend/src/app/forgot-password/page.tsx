'use client';
import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { t } from '@/lib/i18n';

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [resetUrl, setResetUrl] = useState<string | null>(null);
  const [demoNote, setDemoNote] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email) {
      setError('Please enter your email address');
      return;
    }
    setError('');
    setMessage('');
    setResetUrl(null);
    setDemoNote('');
    setLoading(true);
    try {
      const result = await forgotPassword(email);
      setMessage(result.message);
      if (result.reset_url) {
        setResetUrl(result.reset_url);
      }
      if (result.demo_note) {
        setDemoNote(result.demo_note);
      }
    } catch (err: any) {
      setError(err.message || 'Request failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <div className="text-center mb-8">
            <span className="text-3xl">&#x1F511;</span>
            <h1 className="text-2xl font-bold text-gray-900 mt-2">
              {t('auth.forgotPasswordTitle')}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {t('auth.forgotPasswordDesc')}
            </p>
          </div>

          {!message ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('auth.email')}
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all text-sm"
                  placeholder="you@example.com"
                  autoComplete="email"
                  autoFocus
                />
              </div>

              {error && (
                <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {loading ? t('common.loading') : t('auth.sendResetLink')}
              </button>
            </form>
          ) : (
            <div className="space-y-5">
              <div className="bg-green-50 text-green-700 text-sm p-4 rounded-lg leading-relaxed">
                {message}
              </div>

              {demoNote && (
                <div className="bg-amber-50 text-amber-700 text-xs p-3 rounded-lg">
                  &#x1F6C8; {demoNote}
                </div>
              )}

              {resetUrl && (
                <Link
                  href={resetUrl}
                  className="block w-full py-3 bg-indigo-600 text-white text-center font-semibold rounded-xl hover:bg-indigo-700 transition-all"
                >
                  {t('auth.resetPasswordTitle')} &#x2192;
                </Link>
              )}
            </div>
          )}

          <p className="text-center text-sm text-gray-500 mt-6">
            <Link href="/login" className="text-indigo-600 hover:text-indigo-700 font-medium">
              {t('auth.backToLogin')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
