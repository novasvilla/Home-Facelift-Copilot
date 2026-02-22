import { jsPDF } from 'jspdf';

/**
 * Generate a PDF shopping list from the agent's product search response.
 * Extracts product names, prices, and verified store search links.
 *
 * @param {string} text - The full agent response text containing products
 * @param {string} projectName - Name of the project
 * @param {string} sectionName - Name of the section
 */
export function exportShoppingListPDF(text, projectName, sectionName) {
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  const maxWidth = pageWidth - margin * 2;
  let y = 20;

  // Helper: add text and handle page breaks
  const addText = (str, fontSize = 10, style = 'normal', color = [0, 0, 0]) => {
    doc.setFontSize(fontSize);
    doc.setFont('helvetica', style);
    doc.setTextColor(...color);
    const lines = doc.splitTextToSize(str, maxWidth);
    for (const line of lines) {
      if (y > 275) {
        doc.addPage();
        y = 20;
      }
      doc.text(line, margin, y);
      y += fontSize * 0.45;
    }
    y += 2;
  };

  // Helper: add a clickable link
  const addLink = (label, url, fontSize = 9) => {
    if (y > 275) {
      doc.addPage();
      y = 20;
    }
    doc.setFontSize(fontSize);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(0, 102, 204);
    const textWidth = doc.getTextWidth(label);
    doc.textWithLink(label, margin + 4, y, { url });
    doc.line(margin + 4, y + 0.5, margin + 4 + textWidth, y + 0.5);
    y += fontSize * 0.45 + 2;
    doc.setTextColor(0, 0, 0);
  };

  // Title
  addText('LISTA DE COMPRA', 18, 'bold');
  addText(`Proyecto: ${projectName}`, 11, 'normal', [100, 100, 100]);
  addText(`Sección: ${sectionName}`, 11, 'normal', [100, 100, 100]);
  addText(`Fecha: ${new Date().toLocaleDateString('es-ES')}`, 9, 'normal', [150, 150, 150]);
  y += 5;

  // Parse products from the text
  const sections = extractProductSections(text);

  for (const section of sections) {
    // Section header
    addText(section.title, 13, 'bold', [30, 30, 30]);
    y += 2;

    for (const product of section.products) {
      addText(`• ${product.name}`, 10, 'bold');
      if (product.price) {
        addText(`  Precio: ${product.price}`, 9, 'normal', [80, 80, 80]);
      }
      if (product.details) {
        addText(`  ${product.details}`, 8, 'normal', [120, 120, 120]);
      }
      // Add verified store links
      for (const link of product.links) {
        addLink(`  ${link.store}: ${link.url}`, link.url);
      }
      y += 2;
    }
    y += 4;
  }

  // Footer
  y += 5;
  doc.setDrawColor(200, 200, 200);
  doc.line(margin, y, pageWidth - margin, y);
  y += 5;
  addText(
    'Los enlaces de búsqueda directa llevan a la página de resultados de cada tienda. ' +
      'Verifica disponibilidad y precio actual antes de comprar.',
    8,
    'italic',
    [130, 130, 130]
  );
  addText('Generado por Home Facelift Copilot', 8, 'italic', [130, 130, 130]);

  // Save
  const safeName = `${projectName}_${sectionName}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_');
  doc.save(`lista_compra_${safeName}.pdf`);
}

/**
 * Extract product sections from agent response text.
 */
function extractProductSections(text) {
  const sections = [];
  let currentSection = null;

  const lines = text.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();

    // Detect section headers (🎨 MATERIALES, 🛠️ HERRAMIENTAS, etc.)
    if (
      trimmed.match(/^#{1,3}\s/) ||
      trimmed.match(/^[🎨🛠️💰📋🔍]/) ||
      trimmed.match(/^(MATERIALES|HERRAMIENTAS|PRESUPUESTO)/i)
    ) {
      currentSection = {
        title: trimmed.replace(/^#{1,3}\s*/, '').replace(/\*\*/g, ''),
        products: [],
      };
      sections.push(currentSection);
      continue;
    }

    if (!currentSection) {
      currentSection = { title: 'Productos', products: [] };
      sections.push(currentSection);
    }

    // Detect product entries (lines starting with • or - or numbers)
    if (trimmed.match(/^[•\-\d]+[.)]\s/) || trimmed.match(/^\*\*/)) {
      const name = trimmed
        .replace(/^[•\-\d.)\s]+/, '')
        .replace(/\*\*/g, '')
        .trim();
      if (name.length > 3) {
        currentSection.products.push({
          name,
          price: extractPrice(trimmed),
          details: '',
          links: [],
        });
      }
      continue;
    }

    // Detect store links
    const linkMatch = trimmed.match(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/
    );
    if (linkMatch && currentSection.products.length > 0) {
      const lastProduct =
        currentSection.products[currentSection.products.length - 1];
      lastProduct.links.push({
        store: linkMatch[1],
        url: linkMatch[2],
      });
      continue;
    }

    // Detect plain URLs
    const urlMatch = trimmed.match(/(https?:\/\/\S+)/);
    if (urlMatch && currentSection.products.length > 0) {
      const lastProduct =
        currentSection.products[currentSection.products.length - 1];
      const storeName = detectStoreName(urlMatch[1]);
      lastProduct.links.push({
        store: storeName,
        url: urlMatch[1],
      });
      continue;
    }

    // Price lines
    if (
      trimmed.match(/\d+[.,]\d{2}\s*€/) &&
      currentSection.products.length > 0
    ) {
      const lastProduct =
        currentSection.products[currentSection.products.length - 1];
      if (!lastProduct.price) {
        lastProduct.price = extractPrice(trimmed);
      }
    }

    // Details for last product
    if (
      trimmed.length > 5 &&
      currentSection.products.length > 0 &&
      !trimmed.startsWith('#')
    ) {
      const lastProduct =
        currentSection.products[currentSection.products.length - 1];
      if (!lastProduct.details && !trimmed.match(/^[🔗\[\(]/)) {
        lastProduct.details = trimmed.replace(/\*\*/g, '').substring(0, 120);
      }
    }
  }

  // Filter empty sections
  return sections.filter(
    (s) => s.products.length > 0 || s.title.includes('PRESUPUESTO')
  );
}

function extractPrice(text) {
  const match = text.match(/(\d+[.,]\d{2})\s*€/);
  return match ? `${match[1]} €` : null;
}

function detectStoreName(url) {
  if (url.includes('leroymerlin')) return 'Leroy Merlin';
  if (url.includes('manomano')) return 'ManoMano';
  if (url.includes('bricomart')) return 'Bricomart';
  if (url.includes('amazon')) return 'Amazon ES';
  return 'Tienda';
}
