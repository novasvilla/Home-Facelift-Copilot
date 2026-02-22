import { useState, useEffect } from 'react';
import {
  Plus,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  Trash2,
  Palette,
  Home,
} from 'lucide-react';
import {
  getProjects,
  createProject,
  deleteProject,
  addSection,
  deleteSection,
  SECTION_TYPES,
} from '../lib/storage';

export default function Sidebar({ activeProject, activeSection, onSelectSection }) {
  const [projects, setProjects] = useState([]);
  const [expandedProject, setExpandedProject] = useState(null);
  const [showNewProject, setShowNewProject] = useState(false);
  const [showNewSection, setShowNewSection] = useState(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectStyle, setNewProjectStyle] = useState('moderno elegante');
  const [newSectionName, setNewSectionName] = useState('');
  const [newSectionType, setNewSectionType] = useState('exterior');

  useEffect(() => {
    setProjects(getProjects());
  }, []);

  useEffect(() => {
    if (activeProject) setExpandedProject(activeProject.id);
  }, [activeProject]);

  const handleCreateProject = () => {
    if (!newProjectName.trim()) return;
    const p = createProject(newProjectName.trim(), newProjectStyle);
    setProjects(getProjects());
    setExpandedProject(p.id);
    setShowNewProject(false);
    setNewProjectName('');
    setNewProjectStyle('moderno elegante');
  };

  const handleDeleteProject = (e, projectId) => {
    e.stopPropagation();
    if (!confirm('¿Eliminar este proyecto y todas sus secciones?')) return;
    deleteProject(projectId);
    setProjects(getProjects());
  };

  const handleCreateSection = (projectId) => {
    if (!newSectionName.trim()) return;
    const section = addSection(projectId, newSectionName.trim(), newSectionType);
    const updated = getProjects();
    setProjects(updated);
    setShowNewSection(null);
    setNewSectionName('');
    setNewSectionType('exterior');
    const project = updated.find((p) => p.id === projectId);
    if (project && section) onSelectSection(project, section);
  };

  const handleDeleteSection = (e, projectId, sectionId) => {
    e.stopPropagation();
    if (!confirm('¿Eliminar esta sección?')) return;
    deleteSection(projectId, sectionId);
    setProjects(getProjects());
  };

  const sectionIcon = (type) => {
    const found = SECTION_TYPES.find((t) => t.value === type);
    return found ? found.icon : '📐';
  };

  return (
    <aside className="h-full bg-white border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-1">
          <Home size={20} className="text-brand-600" />
          <h1 className="font-bold text-lg text-brand-800">Facelift Copilot</h1>
        </div>
        <p className="text-xs text-gray-400">Proyectos de reforma</p>
      </div>

      {/* Project list */}
      <div className="flex-1 overflow-y-auto p-2">
        {projects.map((project) => (
          <div key={project.id} className="mb-1">
            {/* Project header */}
            <div
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer group
                ${expandedProject === project.id ? 'bg-brand-50 text-brand-700' : 'text-gray-700 hover:bg-gray-100'}`}
            >
              <div
                className="flex-1 flex items-center gap-2 min-w-0"
                onClick={() =>
                  setExpandedProject(
                    expandedProject === project.id ? null : project.id
                  )
                }
              >
                {expandedProject === project.id ? (
                  <ChevronDown size={14} className="shrink-0" />
                ) : (
                  <ChevronRight size={14} className="shrink-0" />
                )}
                <FolderOpen size={16} className="shrink-0" />
                <span className="flex-1 text-left truncate">{project.name}</span>
              </div>
              <button
                onClick={(e) => handleDeleteProject(e, project.id)}
                className="opacity-0 group-hover:opacity-100 hover:text-red-500 p-0.5 shrink-0"
                title="Eliminar proyecto"
              >
                <Trash2 size={13} />
              </button>
            </div>

            {/* Style badge */}
            {expandedProject === project.id && (
              <div className="ml-8 mb-1">
                <span className="inline-flex items-center gap-1 text-[10px] bg-purple-50 text-purple-600 px-2 py-0.5 rounded-full">
                  <Palette size={10} />
                  {project.style}
                </span>
              </div>
            )}

            {/* Sections */}
            {expandedProject === project.id && (
              <div className="ml-4 space-y-0.5">
                {(project.sections || []).map((section) => {
                  const isActive =
                    activeProject?.id === project.id &&
                    activeSection?.id === section.id;
                  return (
                    <div
                      key={section.id}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors group cursor-pointer
                        ${isActive ? 'bg-brand-100 text-brand-800 font-medium' : 'text-gray-600 hover:bg-gray-50'}`}
                    >
                      <div
                        className="flex-1 flex items-center gap-2 min-w-0"
                        onClick={() => onSelectSection(project, section)}
                      >
                        <span>{sectionIcon(section.type)}</span>
                        <span className="flex-1 text-left truncate">
                          {section.name}
                        </span>
                      </div>
                      <button
                        onClick={(e) =>
                          handleDeleteSection(e, project.id, section.id)
                        }
                        className="opacity-0 group-hover:opacity-100 hover:text-red-500 p-0.5 shrink-0"
                        title="Eliminar sección"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                })}

                {/* New section form */}
                {showNewSection === project.id ? (
                  <div className="bg-gray-50 rounded-lg p-2 space-y-2">
                    <input
                      autoFocus
                      value={newSectionName}
                      onChange={(e) => setNewSectionName(e.target.value)}
                      onKeyDown={(e) =>
                        e.key === 'Enter' && handleCreateSection(project.id)
                      }
                      placeholder="Nombre de la sección..."
                      className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 focus:border-brand-400 focus:ring-1 focus:ring-brand-200 outline-none"
                    />
                    <select
                      value={newSectionType}
                      onChange={(e) => setNewSectionType(e.target.value)}
                      className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 focus:border-brand-400 outline-none"
                    >
                      {SECTION_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.icon} {t.label}
                        </option>
                      ))}
                    </select>
                    <div className="flex gap-1">
                      <button
                        onClick={() => handleCreateSection(project.id)}
                        className="flex-1 text-xs bg-brand-600 text-white py-1 rounded hover:bg-brand-700 transition-colors"
                      >
                        Crear
                      </button>
                      <button
                        onClick={() => setShowNewSection(null)}
                        className="flex-1 text-xs bg-gray-200 text-gray-600 py-1 rounded hover:bg-gray-300 transition-colors"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowNewSection(project.id)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-brand-600 transition-colors"
                  >
                    <Plus size={13} />
                    Añadir sección
                  </button>
                )}
              </div>
            )}
          </div>
        ))}

        {/* New project form */}
        {showNewProject ? (
          <div className="bg-gray-50 rounded-lg p-3 space-y-2 mt-2">
            <input
              autoFocus
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
              placeholder="Nombre del proyecto..."
              className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 focus:border-brand-400 focus:ring-1 focus:ring-brand-200 outline-none"
            />
            <input
              value={newProjectStyle}
              onChange={(e) => setNewProjectStyle(e.target.value)}
              placeholder="Estilo (ej: moderno elegante)"
              className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 focus:border-brand-400 outline-none"
            />
            <div className="flex gap-1">
              <button
                onClick={handleCreateProject}
                className="flex-1 text-xs bg-brand-600 text-white py-1.5 rounded hover:bg-brand-700 transition-colors"
              >
                Crear proyecto
              </button>
              <button
                onClick={() => setShowNewProject(false)}
                className="flex-1 text-xs bg-gray-200 text-gray-600 py-1.5 rounded hover:bg-gray-300 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowNewProject(true)}
            className="w-full flex items-center gap-2 px-3 py-2 mt-2 text-sm text-gray-500 hover:text-brand-600 hover:bg-gray-50 rounded-lg transition-colors"
          >
            <Plus size={16} />
            Nuevo proyecto
          </button>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-100 text-[10px] text-gray-400 text-center">
        Home Facelift Copilot v0.9.0
      </div>
    </aside>
  );
}
