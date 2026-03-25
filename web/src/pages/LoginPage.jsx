import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';
import { auth } from '../lib/api';

function PasswordInput({ value, onChange, placeholder, required, minLength, autoComplete }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        placeholder={placeholder}
        className="input-field pr-9"
        value={value}
        onChange={onChange}
      />
      <button
        type="button"
        onClick={() => setShow(v => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none"
        tabIndex={-1}
        title={show ? '隐藏密码' : '显示密码'}
      >
        {show
          ? <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 4.411m0 0L21 21" /></svg>
          : <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
        }
      </button>
    </div>
  );
}

export default function LoginPage() {
  const { t } = useLocale();
  const [searchParams] = useSearchParams();
  const [isRegister, setIsRegister] = useState(searchParams.get('tab') === 'register');

  useEffect(() => {
    setIsRegister(searchParams.get('tab') === 'register');
  }, [searchParams]);
  const [form, setForm] = useState({ emailOrUsername: '', email: '', username: '', password: '', confirmPassword: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (isRegister && form.password !== form.confirmPassword) {
      setError(t('login.passwordMismatch'));
      return;
    }
    setLoading(true);
    try {
      const res = isRegister
        ? await auth.register(form.email, form.username, form.password)
        : await auth.login(form.emailOrUsername, form.password);
      login(res.user, res.access_token);
      navigate('/dashboard');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="min-h-[calc(100vh-48px)] flex items-center justify-center px-4 bg-[#f6f8fa]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-xl font-semibold text-[#24292f]">{isRegister ? t('login.title.register') : t('login.title.login')}</h1>
        </div>
        <form onSubmit={handleSubmit} className="card space-y-3">
          {isRegister ? (
            <>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.email')}</label>
                <input type="email" required className="input-field" value={form.email}
                  onChange={e => setForm({ ...form, email: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.username')}</label>
                <input type="text" required minLength={2} className="input-field" value={form.username}
                  onChange={e => setForm({ ...form, username: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.password')}</label>
                <PasswordInput value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                  required minLength={6} autoComplete="new-password" />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.confirmPassword')}</label>
                <PasswordInput value={form.confirmPassword} onChange={e => setForm({ ...form, confirmPassword: e.target.value })}
                  required minLength={6} autoComplete="new-password" />
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.emailOrUsername')}</label>
                <input type="text" required className="input-field" value={form.emailOrUsername}
                  onChange={e => setForm({ ...form, emailOrUsername: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.password')}</label>
                <PasswordInput value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                  required minLength={6} autoComplete="current-password" />
              </div>
            </>
          )}
          {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</div>}
          <button type="submit" disabled={loading} className="btn-primary w-full !py-2">
            {loading ? t('login.processing') : isRegister ? t('login.submit.register') : t('login.submit.login')}
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-4">
          {isRegister ? t('login.hasAccount') : t('login.noAccount')}
          <button onClick={() => { setIsRegister(!isRegister); setError(''); setForm({ emailOrUsername: '', email: '', username: '', password: '', confirmPassword: '' }); }}
            className="text-[#24292f] font-medium ml-1 cursor-pointer hover:underline">
            {isRegister ? t('login.submit.login') : t('login.submit.register')}
          </button>
        </p>
      </div>
    </div>
  );
}
