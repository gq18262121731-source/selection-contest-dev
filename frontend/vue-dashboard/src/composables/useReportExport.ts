import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { ref } from "vue";

function sanitizeFileSegment(value: string) {
  return value
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function buildFileName(baseName?: string, date = new Date()) {
  if (baseName) {
    const safeName = sanitizeFileSegment(baseName);
    if (safeName) return `${safeName}.pdf`;
  }

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `社区健康交接报告_${year}-${month}-${day}_${hour}-${minute}.pdf`;
}

async function renderPageToCanvas(element: HTMLElement) {
  await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));
  return html2canvas(element, {
    backgroundColor: "#ffffff",
    scale: Math.min(window.devicePixelRatio || 2, 2),
    useCORS: true,
    logging: false,
    width: element.scrollWidth,
    height: element.scrollHeight,
    windowWidth: element.scrollWidth,
    windowHeight: element.scrollHeight,
  });
}

export function useReportExport() {
  const exporting = ref(false);
  const exportError = ref("");

  async function exportReport(target: HTMLElement | null, baseName?: string) {
    if (!target || exporting.value) return;

    exporting.value = true;
    exportError.value = "";

    try {
      const pdf = new jsPDF("p", "mm", "a4");
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const pageElements = Array.from(target.querySelectorAll<HTMLElement>(".pdf-page"));

      if (pageElements.length) {
        for (const [index, page] of pageElements.entries()) {
          const canvas = await renderPageToCanvas(page);
          const imageData = canvas.toDataURL("image/png");
          if (index > 0) pdf.addPage();
          pdf.addImage(imageData, "PNG", 0, 0, pageWidth, pageHeight, undefined, "FAST");
        }
      } else {
        const canvas = await renderPageToCanvas(target);
        const imageData = canvas.toDataURL("image/png");
        const imageWidth = pageWidth;
        const imageHeight = (canvas.height * imageWidth) / canvas.width;

        let heightLeft = imageHeight;
        let position = 0;

        pdf.addImage(imageData, "PNG", 0, position, imageWidth, imageHeight, undefined, "FAST");
        heightLeft -= pageHeight;

        while (heightLeft > 0) {
          position = heightLeft - imageHeight;
          pdf.addPage();
          pdf.addImage(imageData, "PNG", 0, position, imageWidth, imageHeight, undefined, "FAST");
          heightLeft -= pageHeight;
        }
      }

      pdf.save(buildFileName(baseName));
    } catch (error) {
      exportError.value = error instanceof Error ? error.message : "PDF 导出失败，请稍后重试。";
      throw error;
    } finally {
      exporting.value = false;
    }
  }

  return {
    exportError,
    exportReport,
    exporting,
  };
}
