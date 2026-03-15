import { createContext, useContext, useState } from 'react';
import { messages } from '../lib/i18n';

const LocaleContext = createContext(null);

export function LocaleProvider({ children }) {
  const [locale, setLocale] = useState(() => localStorage.getItem('locale') || 'zh');

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
