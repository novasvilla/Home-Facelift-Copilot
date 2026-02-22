/**
 * Parse the agent response text to extract alternatives (A, B, C).
 * Returns an array of { letter, title, concept, body } objects.
 */
export function parseAlternatives(text) {
  if (!text) return [];

  // Split on alternative headers: ## 🅰, ## 🅱, ## 🆎, or ## Alternativa [ABC]
  const pattern =
    /##\s*(?:🅰|🅱|🆎|Alternativa\s+[ABC])[:\s]+(.+?)(?=\n##\s*(?:🅰|🅱|🆎|Alternativa\s+[ABC]|📸|---)|$)/gs;

  const alternatives = [];
  const letters = ['A', 'B', 'C'];
  let idx = 0;
  let match;

  // Simpler approach: split by known headers
  const sections = text.split(/(?=##\s*(?:🅰|🅱|🆎))/);

  for (const section of sections) {
    if (!section.trim()) continue;

    // Check if this section is an alternative
    const headerMatch = section.match(
      /##\s*(?:🅰|🅱|🆎)\s*Alternativa\s+[ABC]:\s*(.+)/
    );
    if (!headerMatch) continue;

    const title = headerMatch[1].trim();

    // Extract concept
    const conceptMatch = section.match(
      /\*\*Concepto\*\*:\s*(.+?)(?=\n\n|\n\|)/s
    );
    const concept = conceptMatch ? conceptMatch[1].trim() : '';

    // The rest is the body (table + CDS)
    const bodyStart = section.indexOf('\n', section.indexOf(title));
    const body = bodyStart >= 0 ? section.slice(bodyStart).trim() : '';

    alternatives.push({
      letter: letters[idx] || String(idx + 1),
      title,
      concept,
      body,
    });
    idx++;
  }

  return alternatives;
}

/**
 * Extract the image status section from the response.
 */
export function parseImageStatus(text) {
  if (!text) return [];
  const images = [];
  const pattern = /\*\*Imagen\s+([ABC])\*\*:\s*(.*)/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    images.push({
      letter: match[1],
      status: match[2].trim(),
      success: match[2].includes('✅'),
    });
  }
  return images;
}

/**
 * Check if a response contains alternatives (Phase 1 output).
 */
export function hasAlternatives(text) {
  if (!text) return false;
  return (
    (text.includes('🅰') || text.includes('Alternativa A')) &&
    (text.includes('🅱') || text.includes('Alternativa B'))
  );
}

/**
 * Check if a response contains a refined proposal (Phase 2 output).
 */
export function isRefinedProposal(text) {
  if (!text) return false;
  return (
    text.includes('Propuesta Refinada') || text.includes('CDS_ACTUALIZADA')
  );
}

/**
 * Extract the section before the image status / separator.
 */
export function extractTextBeforeImages(text) {
  if (!text) return text;
  const sepIdx = text.indexOf('\n---\n');
  return sepIdx >= 0 ? text.slice(0, sepIdx) : text;
}
