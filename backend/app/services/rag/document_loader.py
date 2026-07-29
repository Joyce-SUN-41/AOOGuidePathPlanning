"""文档加载器 — 支持 PDF、TXT、Markdown 格式"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 延迟导入，避免硬依赖
try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


@dataclass
class LoadedPage:
    """文档单页"""

    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class LoadedDocument:
    """加载后的文档"""

    file_path: str
    file_name: str
    file_type: str  # pdf / txt / md
    pages: List[LoadedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)


class DocumentLoader:
    """文档加载器，支持 PDF、TXT、Markdown"""

    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def load_file(cls, file_path: str) -> LoadedDocument:
        """加载单个文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = path.suffix.lower()
        file_name = path.name

        if ext == ".pdf":
            return cls._load_pdf(path, file_name)
        elif ext in (".txt", ".md", ".markdown"):
            return cls._load_text(path, file_name, ext)
        else:
            raise ValueError(f"不支持的文件格式: {ext}，支持: {cls.SUPPORTED_EXTENSIONS}")

    @classmethod
    def load_directory(
        cls,
        directory: str,
        *,
        recursive: bool = True,
        file_patterns: Optional[List[str]] = None,
    ) -> List[LoadedDocument]:
        """批量加载目录中的文档

        Args:
            directory: 目录路径
            recursive: 是否递归子目录
            file_patterns: 文件名 glob 模式列表，如 ["*.pdf", "ch*.md"]

        Returns:
            已加载的文档列表
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"目录不存在: {directory}")

        documents: List[LoadedDocument] = []
        patterns = file_patterns or [f"*{ext}" for ext in cls.SUPPORTED_EXTENSIONS]

        for pattern in patterns:
            glob_method = dir_path.rglob if recursive else dir_path.glob
            for file_path in glob_method(pattern):
                if file_path.is_file() and cls.is_supported(str(file_path)):
                    try:
                        doc = cls.load_file(str(file_path))
                        documents.append(doc)
                        logger.info("Loaded: %s (%d pages)", file_path.name, doc.page_count)
                    except Exception as e:
                        logger.error("Failed to load %s: %s", file_path.name, e)

        logger.info("Directory load complete: %d documents from %s", len(documents), directory)
        return documents

    # ---- PDF ----

    @classmethod
    def _load_pdf(cls, path: Path, file_name: str) -> LoadedDocument:
        if not HAS_PYPDF:
            raise ImportError(
                "PDF 加载需要 pypdf 库: pip install pypdf\n"
                "或运行: poetry add pypdf"
            )

        reader = pypdf.PdfReader(str(path))
        pages: List[LoadedPage] = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(
                    LoadedPage(
                        page_number=i + 1,
                        text=text.strip(),
                        metadata={"page": i + 1, "total_pages": len(reader.pages)},
                    )
                )

        # 提取 PDF 元数据
        pdf_meta = reader.metadata or {}
        metadata = {
            "title": pdf_meta.get("/Title", file_name),
            "author": pdf_meta.get("/Author", ""),
            "subject": pdf_meta.get("/Subject", ""),
            "creator": pdf_meta.get("/Creator", ""),
        }

        logger.debug("PDF loaded: %s | pages=%d", file_name, len(pages))
        return LoadedDocument(
            file_path=str(path),
            file_name=file_name,
            file_type="pdf",
            pages=pages,
            metadata=metadata,
        )

    # ---- TXT / Markdown ----

    @classmethod
    def _load_text(cls, path: Path, file_name: str, ext: str) -> LoadedDocument:
        """加载 TXT 或 Markdown 文件，按章节（##）或空行分页"""
        encoding = cls._detect_encoding(path)
        with open(path, "r", encoding=encoding) as f:
            content = f.read()

        file_type = "md" if ext in (".md", ".markdown") else "txt"

        # 按 Markdown 标题或空行分割为逻辑页
        pages = cls._split_text_to_pages(content, file_type)

        return LoadedDocument(
            file_path=str(path),
            file_name=file_name,
            file_type=file_type,
            pages=pages,
            metadata={"title": file_name, "encoding": encoding},
        )

    @staticmethod
    def _detect_encoding(path: Path) -> str:
        """检测文件编码（尝试 UTF-8 -> GBK -> Latin-1）"""
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(1024)  # 试读前 1KB
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "utf-8"  # fallback

    @classmethod
    def _split_text_to_pages(cls, content: str, file_type: str) -> List[LoadedPage]:
        """将文本按结构分割为逻辑页"""
        pages: List[LoadedPage] = []
        page_num = 1

        if file_type == "md":
            # Markdown: 按 ## 标题分割
            import re

            # 保留章节标题的分割
            sections = re.split(r"\n(?=#{1,3}\s)", content)
            for section in sections:
                section = section.strip()
                if section:
                    pages.append(
                        LoadedPage(page_number=page_num, text=section, metadata={"section": page_num})
                    )
                    page_num += 1
        else:
            # TXT: 按空行分割，合并过短的片段
            paragraphs = content.split("\n\n")
            buffer = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                buffer += para + "\n\n"
                if len(buffer) > 500:
                    pages.append(
                        LoadedPage(page_number=page_num, text=buffer.strip(), metadata={"section": page_num})
                    )
                    page_num += 1
                    buffer = ""
            if buffer.strip():
                pages.append(
                    LoadedPage(page_number=page_num, text=buffer.strip(), metadata={"section": page_num})
                )

        logger.debug("Text split into %d logical pages", len(pages))
        return pages
