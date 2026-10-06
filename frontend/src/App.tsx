import { Route, Routes } from 'react-router-dom'

import { Header } from './components/Header.tsx'
import { CaseView } from './pages/CaseView.tsx'
import { QueueView } from './pages/QueueView.tsx'

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <Routes>
        <Route path="/" element={<QueueView />} />
        <Route path="/cases/:id" element={<CaseView />} />
      </Routes>
    </div>
  )
}
