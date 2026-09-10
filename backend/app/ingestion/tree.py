from app.ingestion.models import Section


class SectionTreeBuilder:
    """栈式构建标题层级树；MD/PDF/DOCX 解析共用。"""

    def __init__(self) -> None:
        self._root = Section(level=0, title="__root__")
        self._stack: list[Section] = [self._root]

    def _current(self) -> Section:
        return self._stack[-1]

    def add_heading(self, level: int, title: str) -> None:
        while self._stack[-1].level >= level:
            self._stack.pop()
        node = Section(level=level, title=title)
        self._stack[-1].children.append(node)
        self._stack.append(node)

    def add_text(self, line: str) -> None:
        if not line.strip():
            return
        cur = self._current()
        cur.text = f"{cur.text}\n{line.strip()}".strip()

    def add_table(self, md_text: str, title: str, page: int | None = None) -> None:
        self._stack[-1].children.append(
            Section(
                level=self._stack[-1].level + 1,
                title=title,
                text=md_text.strip(),
                page=page,
                is_table=True,
            )
        )

    def build(self) -> list[Section]:
        return self._root.children if self._root.children else [self._root]
