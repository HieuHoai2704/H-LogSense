"""Render bounded project PDF pages without running PDF scripts or actions."""

from contextlib import closing
from io import BytesIO
from math import isfinite
from threading import Lock

from app.workbench.files import WorkspaceError

MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_PAGE_PIXELS = 2200
PDFIUM_LOCK = Lock()


def render_page(path, index, zoom):
    import pypdfium2 as pdf

    if path.suffix.casefold() != ".pdf" or not path.is_file():
        raise WorkspaceError("Choose a PDF file in the project.")
    with path.open("rb") as stream:
        if path.stat().st_size > MAX_PDF_BYTES:
            raise WorkspaceError("Preview supports PDFs up to 32 MiB.", 413)
        data = stream.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise WorkspaceError("Preview supports PDFs up to 32 MiB.", 413)
    # PDFium uses process-global state. Serialize rendering across both panes.
    with PDFIUM_LOCK:
        try:
            with pdf.PdfDocument(data) as document:
                pages = len(document)
                if index >= pages:
                    raise WorkspaceError("PDF page is out of range.")
                with closing(document[index]) as page:
                    width, height = page.get_size()
                    if not all(isfinite(value) and value > 0 for value in (width, height)):
                        raise WorkspaceError("PDF page size is invalid.")
                    scale = min(zoom / 100, MAX_PAGE_PIXELS / max(width, height))
                    with closing(page.render(scale=scale)) as bitmap:
                        output = BytesIO()
                        bitmap.to_pil().save(output, format="PNG")
                    return output.getvalue(), pages
        except pdf.PdfiumError as error:
            raise WorkspaceError(
                "Could not read the PDF. The file may be corrupted or password-protected.", 422
            ) from error
