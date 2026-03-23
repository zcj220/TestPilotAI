import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import TestPage from './pages/TestPage';
import RunningPage from './pages/RunningPage';
import HistoryPage from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage';
import HelpPage from './pages/HelpPage';
import AnalyticsPage from './pages/AnalyticsPage';
import DashboardPage from './pages/DashboardPage';
import TeamPage from './pages/TeamPage';
import DesktopTestPage from './pages/DesktopTestPage';
import MiniProgramTestPage from './pages/MiniProgramTestPage';
import MultiPlayerTestPage from './pages/MultiPlayerTestPage';
import TermsPage from './pages/TermsPage';
import PrivacyPage from './pages/PrivacyPage';
import RefundPage from './pages/RefundPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<TestPage />} />
          <Route path="/running" element={<RunningPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/team" element={<TeamPage />} />
          <Route path="/desktop-test" element={<DesktopTestPage />} />
          <Route path="/miniprogram-test" element={<MiniProgramTestPage />} />
          <Route path="/multiplayer-test" element={<MultiPlayerTestPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
        </Route>
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/refund" element={<RefundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
