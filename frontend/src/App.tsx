import { useEffect, useState } from 'react'
import './App.css'

export default function App() {
  const [healthStatus, setHealthStatus] = useState<string>('Checking...')

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then((res) => res.json())
      .then((data) => setHealthStatus(`Backend: ${data.status}`))
      .catch(() => setHealthStatus('Backend: offline (or starting)'))
  }, [])

  return (
    <div className="container" id="app-root">
      <div className="card">
        <header className="header">
          <div className="badge">Phase 0 - Initial Setup</div>
          <h1 id="app-title">CloudDeploy Lite</h1>
          <p className="subtitle">
            A beginner-friendly deployment platform skeleton.
          </p>
        </header>

        <section className="status-section">
          <div className="status-item">
            <span className="dot dot-frontend"></span>
            <span>Frontend: <strong>Running (React + Vite)</strong></span>
          </div>
          <div className="status-item">
            <span className="dot dot-backend"></span>
            <span id="backend-status">{healthStatus}</span>
          </div>
        </section>

        <footer className="footer">
          <p>Repository initialized successfully.</p>
        </footer>
      </div>
    </div>
  )
}
