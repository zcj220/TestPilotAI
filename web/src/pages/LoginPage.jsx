import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';
import { auth } from '../lib/api';

export default function LoginPage() {
  const { t } = useLocale();
  const [searchParams] = useSearchParams();
  const [isRegister, setIsRegister] = useState(searchParams.get('tab') === 'register');

  useEffect(() => {
    setIsRegister(searchParams.get('tab') === 'register');
  }, [searchParams]);
  const [form, setForm] = useState({ email: '', username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = isRegister
        ? await auth.register(form.email, form.username, form.password)
        : await auth.login(form.email, form.password);
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
          <div>
            <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.email')}</label>
            <input type="email" required className="input-field" value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })} />
          </div>
          {isRegister && (
            <div>
              <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.username')}</label>
              <input type="text" required minLength={2} className="input-field" value={form.username}
                onChange={e => setForm({ ...form, username: e.target.value })} />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-[#24292f] mb-1">{t('login.password')}</label>
            <input type="password" required minLength={6} className="input-field" value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })} />
          </div>
          {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</div>}
          <button type="submit" disabled={loading} className="btn-primary w-full !py-2">
            {loading ? t('login.processing') : isRegister ? t('login.submit.register') : t('login.submit.login')}
          </button>
        </form>
        <p className="text-center text-xs text-gray-500 mt-4">
          {isRegister ? t('login.hasAccount') : t('login.noAccount')}
          <button onClick={() => { setIsRegister(!isRegister); setError(''); }}
            className="text-[#24292f] font-medium ml-1 cursor-pointer hover:underline">
            {isRegister ? t('login.submit.login') : t('login.submit.register')}
          </button>
        </p>
      </div>
    </div>
  );
}
