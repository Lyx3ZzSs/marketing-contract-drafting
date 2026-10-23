"""Bounded, isolated LibreOffice conversion; no HTTP or database responsibilities."""

import os
import signal
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import get_settings
from app.preview_files import MAX_PDF_BYTES


def convert_pdf(docx: bytes) -> bytes:
    settings = get_settings()
    with TemporaryDirectory(prefix="contract-render-") as directory:
        root = Path(directory)
        source = root / "contract.docx"
        source.write_bytes(docx)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        # No macros or external-link updates in an unattended document renderer.
        (profile / "user" / "registrymodifications.xcu").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
            '<item oor:path="/org.openoffice.Office.Writer/Content/Update">'
            '<prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item></oor:items>',
            encoding="utf-8",
        )
        command = [
            settings.libreoffice_binary,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            directory,
            str(source),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ValueError("PDF 转换服务未安装 LibreOffice") from exc
        try:
            process.wait(timeout=settings.preview_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("合同排版超时，请重试") from exc
        finally:
            # Also handles Celery's soft time limit; do not leave soffice children behind.
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        target = root / "contract.pdf"
        if process.returncode != 0 or not target.exists():
            raise ValueError("合同 PDF 转换失败，请检查模板格式")
        if target.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("预览文件超过 32 MB 限制")
        data = target.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError("转换未产生有效的 PDF 文件")
        return data
