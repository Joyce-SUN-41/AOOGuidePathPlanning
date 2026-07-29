"""文档分块器 — 智能分割文档为语义块"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """文档块"""

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0

    @property
    def source_label(self) -> str:
        """生成人类可读的来源标签"""
        doc = self.metadata.get("document", "未知文档")
        page = self.metadata.get("page", "")
        section = self.metadata.get("section", "")
        parts = [doc]
        if page:
            parts.append(f"第{page}页")
        if section:
            parts.append(section)
        return " · ".join(parts)


class ChunkConfig:
    """分块配置"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        min_chunk_size: int = 100,
        separators: Optional[List[str]] = None,
    ):
        """
        Args:
            chunk_size: 目标块大小（字符数）
            chunk_overlap: 块重叠大小
            min_chunk_size: 最小块大小（短于此值的块会与前一块合并）
            separators: 分割符优先级列表
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.separators = separators or [
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            "；",
            "，",
            " ",
            "",
        ]


class DocumentChunker:
    """递归字符分割器，保留章节/页码等元数据"""

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    def chunk_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """将完整文本分割为语义块列表"""
        base_meta = metadata or {}
        raw_splits = self._split_text(text)

        chunks: List[Chunk] = []
        current_chunk = ""
        chunk_idx = 0

        for split in raw_splits:
            split = split.strip()
            if not split:
                continue

            # 如果当前块 + 新段落仍在大小限制内，追加
            if current_chunk and len(current_chunk) + len(split) + 1 <= self.config.chunk_size:
                current_chunk += "\n" + split
            else:
                # 保存当前块
                if current_chunk and len(current_chunk) >= self.config.min_chunk_size:
                    chunks.append(
                        Chunk(
                            content=current_chunk.strip(),
                            metadata={**base_meta, "chunk_index": chunk_idx},
                            chunk_index=chunk_idx,
                        )
                    )
                    chunk_idx += 1
                    # 创建重叠：保留当前块的尾部作为新块的前缀
                    current_chunk = self._create_overlap(current_chunk) + split
                else:
                    current_chunk = (current_chunk + "\n" + split).strip() if current_chunk else split

        # 保存最后一个块
        if current_chunk and len(current_chunk) >= self.config.min_chunk_size:
            chunks.append(
                Chunk(
                    content=current_chunk.strip(),
                    metadata={**base_meta, "chunk_index": chunk_idx},
                    chunk_index=chunk_idx,
                )
            )
        elif current_chunk and chunks:
            # 合并到前一个块
            chunks[-1].content += "\n" + current_chunk

        logger.debug("Document chunked: %d chunks from %d chars", len(chunks), len(text))
        return chunks

    def _split_text(self, text: str) -> List[str]:
        """递归按分隔符分割文本"""
        return self._recursive_split(text, self.config.separators)

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """递归分割：用当前分隔符分割，如果片段过大则用下一级分隔符"""
        if not separators:
            # 无分隔符可用，强制按长度分割
            result: List[str] = []
            for i in range(0, len(text), self.config.chunk_size):
                result.append(text[i : i + self.config.chunk_size])
            return result

        sep = separators[0]
        remaining = separators[1:]

        if sep == "":
            # 字符级分割
            result = []
            for i in range(0, len(text), self.config.chunk_size):
                result.append(text[i : i + self.config.chunk_size])
            return result

        parts = text.split(sep)
        final_splits: List[str] = []

        for part in parts:
            if len(part) <= self.config.chunk_size:
                if part.strip():
                    final_splits.append(part)
            else:
                # 片段过大，用下一级分隔符递归分割
                sub_splits = self._recursive_split(part, remaining)
                final_splits.extend(sub_splits)

        return final_splits

    def _create_overlap(self, text: str) -> str:
        """提取文本尾部作为重叠上下文"""
        if len(text) <= self.config.chunk_overlap:
            return text + "\n"
        # 在合理位置截断（优先断句）
        overlap_text = text[-self.config.chunk_overlap :]
        # 跳过开头的不完整句子
        for sep in ["。", "！", "？", "\n", "，"]:
            idx = overlap_text.find(sep)
            if idx > 0 and idx < len(overlap_text) // 3:
                overlap_text = overlap_text[idx + 1 :]
                break
        return overlap_text + "\n"


class MarkdownChunker(DocumentChunker):
    """Markdown 专用分块器：按标题层级优先分割"""

    def chunk_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        base_meta = metadata or {}

        # 先按 ## 标题分割为节
        sections = self._split_by_headings(text)

        all_chunks: List[Chunk] = []
        chunk_idx = 0

        for section_title, section_text in sections:
            section_meta = {**base_meta}
            if section_title:
                section_meta["section"] = section_title.strip("# ").strip()

            # 对每节再按常规方式分块
            sub_chunks = super().chunk_document(section_text, section_meta)
            for chunk in sub_chunks:
                chunk.chunk_index = chunk_idx
                chunk.metadata["chunk_index"] = chunk_idx
                chunk_idx += 1
            all_chunks.extend(sub_chunks)

        logger.debug("Markdown chunked: %d chunks from %d chars", len(all_chunks), len(text))
        return all_chunks

    @staticmethod
    def _split_by_headings(text: str) -> List[tuple]:
        """按 Markdown 标题分割，返回 [(标题, 内容)]"""
        # 匹配行首的 # ~ ### 标题
        heading_pattern = re.compile(r"^(#{1,3}\s+.+)$", re.MULTILINE)

        matches = list(heading_pattern.finditer(text))
        if not matches:
            return [("", text)]

        sections: List[tuple] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            title = match.group(1)
            content = text[start:end].strip()
            sections.append((title, content))

        # 标题前的内容作为无标题段落
        if matches and matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.insert(0, ("", preamble))

        return sections
