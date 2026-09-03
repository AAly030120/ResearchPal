'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { t } from '@/lib/i18n';

const features = [
  {
    key: 'summary',
    icon: '\u{1F4D6}',
    href: '/tools/summary',
  },
  {
    key: 'ppt',
    icon: '\u{1F4CA}',
    href: '/tools/ppt',
  },
  {
    key: 'analysis',
    icon: '\u{1F4C8}',
    href: '/tools/analysis',
  },
  {
    key: 'codegen',
    icon: '\u{1F4BB}',
    href: '/tools/codegen',
  },
  {
    key: 'translate',
    icon: '\u{1F30D}',
    href: '/tools/translate',
  },
];

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div>
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-indigo-600 via-indigo-500 to-purple-600 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-32">
          <div className="text-center max-w-3xl mx-auto">
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6">
              {t('home.hero.title')}
            </h1>
            <p className="text-lg md:text-xl text-indigo-100 mb-10">
              {t('home.hero.subtitle')}
            </p>
            <Link
              href={user ? '/dashboard' : '/register'}
              className="inline-flex items-center px-8 py-4 bg-white text-indigo-600 font-semibold rounded-xl hover:bg-indigo-50 transition-colors shadow-lg text-lg"
            >
              {t('home.hero.cta')}
              <svg className="ml-2 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
            {t('app.tagline')}
          </h2>
          <p className="text-gray-500 max-w-2xl mx-auto">
            五大核心功能，覆盖科研全流程
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature) => (
            <Link
              key={feature.key}
              href={user ? feature.href : '/login'}
              className="group bg-white rounded-2xl p-8 shadow-sm border border-gray-100 hover:shadow-md hover:border-indigo-100 transition-all"
            >
              <div className="text-4xl mb-4">{feature.icon}</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2 group-hover:text-indigo-600 transition-colors">
                {t(`home.feature.${feature.key}.title`)}
              </h3>
              <p className="text-gray-500 text-sm leading-relaxed">
                {t(`home.feature.${feature.key}.desc`)}
              </p>
            </Link>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-indigo-50 py-20">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            开始你的科研之旅
          </h2>
          <p className="text-gray-600 mb-8">
            注册即可免费使用所有工具，让 AI 帮你提升科研效率
          </p>
          <Link
            href={user ? '/dashboard' : '/register'}
            className="inline-flex items-center px-8 py-4 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition-colors shadow-lg text-lg"
          >
            {user ? t('nav.dashboard') : t('home.hero.cta')}
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-100 py-8">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-gray-400">
          &copy; 2026 ResearchPal. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
