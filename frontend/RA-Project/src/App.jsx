import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import UploadPage from './pages/UploadPage';
import DashboardPage from './pages/DashboardPage';
import ReflectionPage from './pages/ReflectionPage';
import ExportPage from './pages/ExportPage';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/dashboard/:datasetId" element={<DashboardPage />} />
          <Route path="/reflection/:datasetId" element={<ReflectionPage />} />
          <Route path="/export/:datasetId" element={<ExportPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
