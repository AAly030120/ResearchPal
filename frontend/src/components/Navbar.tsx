'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { t, getLanguage, setLanguage } from '@/lib/i18n';

export default function Navbar() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [lang, setLang] = useState(getLanguage());

  const toggleLang = (l: string) => {
    setLang(l);
    setLanguage(l);
  };

  return (
    <nav className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center space-x-2">
            <span className="text-2xl">&#x1F52C;</span>
            <span className="text-xl font-bold text-indigo-600">{t('app.name')}</span>
          </Link>

          {/* Desktop nav links */}
          <div className="hidden md:flex items-center space-x-6">
            <Link href="/" className="text-gray-600 hover:text-indigo-600 transition-colors text-sm font-medium">
              {t('nav.home')}
            </Link>
            {user && (
              <>
                <Link href="/dashboard" className="text-gray-600 hover:text-indigo-600 transition-colors text-sm font-medium">
                  {t('nav.dashboard')}
                </Link>
                <Link href="/chat" className="text-gray-600 hover:text-indigo-600 transition-colors text-sm font-medium">
                  {t('nav.chat')}
                </Link>
                <Link href="/settings" className="text-gray-600 hover:text-indigo-600 transition-colors text-sm font-medium">
                  {t('nav.settings')}
                </Link>
              </>
            )}
          </div>

          {/* Right side: language toggle + auth */}
          <div className="hidden md:flex items-center space-x-4">
            {/* Language toggle */}
            <div className="flex items-center space-x-1 bg-gray-100 rounded-lg p-0.5">
              <button
                onClick={() => toggleLang('zh')}
                className={`px-2 py-1 text-xs rounded-md transition-colors ${
                  lang === 'zh' ? 'bg-white shadow text-indigo-600 font-semibold' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                中文
              </button>
              <button
                onClick={() => toggleLang('en')}
                className={`px-2 py-1 text-xs rounded-md transition-colors ${
                  lang === 'en' ? 'bg-white shadow text-indigo-600 font-semibold' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                EN
              </button>
            </div>

            {/* Auth buttons */}
            {user ? (
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center space-x-2 text-sm text-gray-700 hover:text-indigo-600 transition-colors"
                >
                  <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center">
                    <span className="text-indigo-600 font-semibold text-sm">
                      {user.username.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <span className="font-medium">{user.username}</span>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {userMenuOpen && (
                  <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-50">
                    <button
                      onClick={() => { logout(); setUserMenuOpen(false); }}
                      className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      {t('nav.logout')}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center space-x-2">
                <Link
                  href="/login"
                  className="text-sm text-gray-600 hover:text-indigo-600 font-medium px-3 py-2"
                >
                  {t('nav.login')}
                </Link>
                <Link
                  href="/register"
                  className="text-sm bg-indigo-600 text-white hover:bg-indigo-700 font-medium px-4 py-2 rounded-lg transition-colors"
                >
                  {t('nav.register')}
                </Link>
              </div>
            )}
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-2 rounded-md text-gray-600 hover:text-indigo-600 hover:bg-gray-100"
          >
            {mobileOpen ? (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="md:hidden border-t border-gray-100 py-4 space-y-3">
            <Link href="/" onClick={() => setMobileOpen(false)} className="block px-2 py-2 text-gray-600 hover:text-indigo-600 text-sm font-medium">
              {t('nav.home')}
            </Link>
            {user && (
              <>
                <Link href="/dashboard" onClick={() => setMobileOpen(false)} className="block px-2 py-2 text-gray-600 hover:text-indigo-600 text-sm font-medium">
                  {t('nav.dashboard')}
                </Link>
                <Link href="/chat" onClick={() => setMobileOpen(false)} className="block px-2 py-2 text-gray-600 hover:text-indigo-600 text-sm font-medium">
                  {t('nav.chat')}
                </Link>
                <Link href="/settings" onClick={() => setMobileOpen(false)} className="block px-2 py-2 text-gray-600 hover:text-indigo-600 text-sm font-medium">
                  {t('nav.settings')}
                </Link>
              </>
            )}
            {/* Language toggle mobile */}
            <div className="flex items-center space-x-1 px-2">
              <button
                onClick={() => toggleLang('zh')}
                className={`px-3 py-1.5 text-xs rounded-md ${
                  lang === 'zh' ? 'bg-indigo-100 text-indigo-600 font-semibold' : 'text-gray-500'
                }`}
              >
                中文
              </button>
              <button
                onClick={() => toggleLang('en')}
                className={`px-3 py-1.5 text-xs rounded-md ${
                  lang === 'en' ? 'bg-indigo-100 text-indigo-600 font-semibold' : 'text-gray-500'
                }`}
              >
                EN
              </button>
            </div>
            {user ? (
              <button
                onClick={() => { logout(); setMobileOpen(false); }}
                className="block w-full text-left px-2 py-2 text-red-600 hover:bg-red-50 text-sm font-medium"
              >
                {t('nav.logout')}
              </button>
            ) : (
              <div className="flex flex-col space-y-2 px-2">
                <Link href="/login" onClick={() => setMobileOpen(false)} className="block py-2 text-gray-600 hover:text-indigo-600 text-sm">
                  {t('nav.login')}
                </Link>
                <Link href="/register" onClick={() => setMobileOpen(false)} className="block py-2 text-indigo-600 font-medium text-sm">
                  {t('nav.register')}
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}
