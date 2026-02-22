const STORAGE_KEY = 'hfc_projects';

function loadAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAll(projects) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
}

export function getProjects() {
  return loadAll();
}

export function getProject(projectId) {
  return loadAll().find((p) => p.id === projectId) || null;
}

export function createProject(name, style = 'moderno elegante') {
  const projects = loadAll();
  const id = name
    .toLowerCase()
    .replace(/[^a-z0-9áéíóúñü]+/g, '_')
    .replace(/^_|_$/g, '');
  const project = {
    id,
    name,
    style,
    createdAt: new Date().toISOString(),
    sections: [],
  };
  projects.push(project);
  saveAll(projects);
  return project;
}

export function updateProjectStyle(projectId, style) {
  const projects = loadAll();
  const p = projects.find((p) => p.id === projectId);
  if (p) {
    p.style = style;
    saveAll(projects);
  }
  return p;
}

export function deleteProject(projectId) {
  const projects = loadAll().filter((p) => p.id !== projectId);
  saveAll(projects);
}

export function addSection(projectId, name, type = 'exterior') {
  const projects = loadAll();
  const p = projects.find((p) => p.id === projectId);
  if (!p) return null;

  const id = name
    .toLowerCase()
    .replace(/[^a-z0-9áéíóúñü]+/g, '_')
    .replace(/^_|_$/g, '');

  const section = {
    id,
    name,
    type,
    sessionId: `${projectId}__${id}`,
    createdAt: new Date().toISOString(),
  };

  p.sections = p.sections || [];
  p.sections.push(section);
  saveAll(projects);
  return section;
}

export function deleteSection(projectId, sectionId) {
  const projects = loadAll();
  const p = projects.find((p) => p.id === projectId);
  if (p) {
    p.sections = (p.sections || []).filter((s) => s.id !== sectionId);
    saveAll(projects);
  }
}

export const SECTION_TYPES = [
  { value: 'exterior', label: 'Fachada / Exterior', icon: '🏠' },
  { value: 'interior', label: 'Interior / Salón', icon: '🛋️' },
  { value: 'baño', label: 'Baño', icon: '🚿' },
  { value: 'cocina', label: 'Cocina', icon: '🍳' },
  { value: 'dormitorio', label: 'Dormitorio', icon: '🛏️' },
  { value: 'jardín', label: 'Jardín / Terraza', icon: '🌿' },
  { value: 'garaje', label: 'Garaje', icon: '🚗' },
  { value: 'otro', label: 'Otro', icon: '📐' },
];
