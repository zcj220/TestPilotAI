import { createContext, useContext, useState } from 'react';
import { messages } from '../lib/i18n';

const LocaleContext = createContext(null);

export function LocaleProvider({ children }) {
  const [locale, setLocale] = useState(() => {
    const saved = localStorage.getItem('locale');
    if (saved) return saved;
    // 国际站（pages.dev 或未来绑定的 .com 域名）默认英文，国内站默认中文
    const host = window.location.hostname;
    if (host.includes('pages.dev') || host.includes('.com')) return 'en';
    return 'zh';
  });

  function changeLocale(l) {
    setLocale(l);
    localStorage.setItem('locale', l);
  }

  function t(key) {
    return messages[locale]?.[key] || messages.zh[key] || key;
  }

  return (
    <LocaleContext.Provider value={{ locale, setLocale: changeLocale, t }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale must be used within LocaleProvider');
  return ctx;
}
