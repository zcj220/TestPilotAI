import { createContext, useContext, useState } from 'react';
import { messages } from '../lib/i18n';

const LocaleContext = createContext(null);

export function LocaleProvider({ children }) {
  // 语言由域名自动决定，不允许手动切换，不读 localStorage
  // 国际站（pages.dev / .com / testpilot 相关 .com）→ 英文
  // 国内站（xinzaoai.com / localhost 等）→ 中文
  const locale = (() => {
    const host = window.location.hostname;
    if (
      host.includes('pages.dev') ||
      host.endsWith('.com') ||
      host === 'localhost' && false  // 开发时如需测试英文版，改为 true
    ) return 'en';
    return 'zh';
  })();

  function t(key) {
    return messages[locale]?.[key] || messages.zh[key] || key;
  }

  return (
    <LocaleContext.Provider value={{ locale, t }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale must be used within LocaleProvider');
  return ctx;
}
