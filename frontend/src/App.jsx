import { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import { Menu, X } from 'lucide-react';

export default function App() {
  const [activeProject, setActiveProject] = useState(null);
  const [activeSection, setActiveSection] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleSelectSection = useCallback((project, section) => {
    setActiveProject(project);
    setActiveSection(section);
    // Auto-close sidebar on mobile
    if (window.innerWidth < 768) setSidebarOpen(false);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="fixed top-3 left-3 z-50 md:hidden bg-white shadow-lg rounded-lg p-2 hover:bg-gray-100 transition-colors"
        aria-label="Toggle sidebar"
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 w-72 transform transition-transform duration-200 ease-in-out
          md:relative md:translate-x-0
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <Sidebar
          activeProject={activeProject}
          activeSection={activeSection}
          onSelectSection={handleSelectSection}
        />
      </div>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {activeProject && activeSection ? (
          <ChatPanel
            project={activeProject}
            section={activeSection}
            key={`${activeProject.id}__${activeSection.id}`}
          />
        ) : (
          <EmptyState />
        )}
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">🏠</div>
        <h2 className="text-2xl font-bold text-gray-800 mb-2">
          Home Facelift Copilot
        </h2>
        <p className="text-gray-500 mb-6">
          Selecciona o crea un proyecto de reforma y una sección para comenzar.
          Sube una foto y el copiloto generará 3 alternativas de diseño moderno.
        </p>
        <div className="grid grid-cols-2 gap-3 text-sm text-gray-600">
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <span className="text-lg">📸</span>
            <p className="mt-1">Sube foto de la zona</p>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <span className="text-lg">🎨</span>
            <p className="mt-1">3 alternativas de diseño</p>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <span className="text-lg">✏️</span>
            <p className="mt-1">Refina a tu gusto</p>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <span className="text-lg">🛒</span>
            <p className="mt-1">Lista de compra</p>
          </div>
        </div>
      </div>
    </div>
  );
}
