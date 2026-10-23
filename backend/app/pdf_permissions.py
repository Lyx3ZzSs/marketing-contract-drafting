"""PDF download permissions, without changing the preview or source document."""

import io
import secrets

import pikepdf


def readonly_pdf(data: bytes) -> bytes:
    """Allow password-free reading/printing; request no edits in compliant viewers."""
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(data)) as document:
        document.save(
            output,
            encryption=pikepdf.Encryption(
                owner=secrets.token_urlsafe(32),
                user="",
                R=6,
                allow=pikepdf.Permissions(
                    modify_annotation=False,
                    modify_assembly=False,
                    modify_form=False,
                    modify_other=False,
                    extract=True,
                    accessibility=True,
                    print_lowres=True,
                    print_highres=True,
                ),
            ),
        )
    return output.getvalue()
