import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';
import { community } from '../lib/api';
import { PLATFORMS, DIFFICULTIES } from '../lib/constants';

export default function SharePage() {
  const { user } = useAuth();
  const { t } = useLocale();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    title: '', platform: 'web', framework: '', error_type: '',
    problem_desc: '', solution_desc: '', root_cause: '', code_snippet: '',
    tags: '', difficulty: 'medium',
  });

  if (!user) { navigate('/login'); return null; }

  function set(k, v) { setForm(prev => ({ ...prev, [k]: v })); }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = { ...form, tags: form.tags ? form.tags.split(',').map(s => s.trim()).filter(Boolean) : [] };
      const res = await community.create(data);
      navigate(`/experience/${res.experience.id}`);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 lg:px-8 py-6">
      <div className="border-b border-[#d1d9e0] pb-4 mb-6">
        <h1 className="text-xl font-semibold text-[#24292f]">{t('share.title')}</h1>
        <p className="text-sm text-gray-500 mt-1">{t('share.subtitle')}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.titleField')} *</label>
          <input type="text" required minLength={2} maxLength={200} className="input-field"
            placeholder="e.g. Playwright locator timeout fix" value={form.title} onChange={e => set('title', e.target.value)} />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.platform')} *</label>
            <select className="input-field" value={form.platform} onChange={e => set('platform', e.target.value)}>
              {PLATFORMS.map(p => <option key={p.value} value={p.value}>{t(`platform.${p.value}`)}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.framework')}</label>
            <input type="text" className="input-field" placeholder="React, Flutter..." value={form.framework} onChange={e => set('framework', e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.difficulty')}</label>
            <select className="input-field" value={form.difficulty} onChange={e => set('difficulty', e.target.value)}>
              {DIFFICULTIES.map(d => <option key={d.value} value={d.value}>{t(`difficulty.${d.value}`)}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.errorType')}</label>
          <input type="text" className="input-field" placeholder="TimeoutError, ElementNotFound..." value={form.error_type} onChange={e => set('error_type', e.target.value)} />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.problem')} *</label>
          <textarea required minLength={10} rows={3} className="input-field"
            value={form.problem_desc} onChange={e => set('problem_desc', e.target.value)} />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.solution')} *</label>
          <textarea required minLength={10} rows={3} className="input-field"
            value={form.solution_desc} onChange={e => set('solution_desc', e.target.value)} />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.rootCause')}</label>
          <textarea rows={2} className="input-field"
            value={form.root_cause} onChange={e => set('root_cause', e.target.value)} />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.code')}</label>
          <textarea rows={3} className="input-field font-mono text-xs"
            value={form.code_snippet} onChange={e => set('code_snippet', e.target.value)} />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#24292f] mb-1">{t('share.tags')}</label>
          <input type="text" className="input-field" placeholder="timeout, spa, playwright"
            value={form.tags} onChange={e => set('tags', e.target.value)} />
        </div>

        {error && <div className="text-sm text-[#cf222e] bg-[#ffebe9] border border-[#ff8182] rounded-md px-3 py-2">{error}</div>}

        <div className="flex items-center gap-3 pt-2">
          <button type="submit" disabled={loading} className="btn-primary">{loading ? t('share.submitting') : t('share.submit')}</button>
          <button type="button" onClick={() => navigate(-1)} className="btn-secondary">{t('share.cancel')}</button>
        </div>
      </form>
    </div>
  );
}
