import io

import pikepdf

from app.pdf_permissions import readonly_pdf


def test_download_permissions_preserve_pages_and_allow_password_free_reading() -> None:
    original = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        page = document.add_blank_page(page_size=(595, 842))
        page.Contents = document.make_stream(b"q 1 0 0 1 0 0 cm Q")
        document.save(original)
    data = readonly_pdf(original.getvalue())
    with pikepdf.Pdf.open(io.BytesIO(data)) as result:
        assert result.is_encrypted
        assert result.user_password_matched and not result.owner_password_matched
        assert result.encryption.R == 6
        assert len(result.pages) == 1
        assert result.pages[0].Contents.read_bytes() == b"q 1 0 0 1 0 0 cm Q"
        assert result.allow.extract and result.allow.print_highres
        assert not result.allow.modify_annotation
        assert not result.allow.modify_assembly
        assert not result.allow.modify_form
        assert not result.allow.modify_other
    with pikepdf.Pdf.open(io.BytesIO(original.getvalue())) as source:
        assert not source.is_encrypted
