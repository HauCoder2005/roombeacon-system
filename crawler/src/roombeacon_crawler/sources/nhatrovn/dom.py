from html.parser import HTMLParser
from typing import Callable


class DOMNode:
    """Đại diện cho một node phần tử trong cây DOM thu nhỏ phục vụ trích xuất HTML."""

    def __init__(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        parent: "DOMNode | None" = None,
    ) -> None:
        self.tag = tag.lower()
        self.attrs: dict[str, str] = {k.lower(): (v or "") for k, v in attrs}
        self.parent = parent
        self.children: list[DOMNode] = []
        self.text_parts: list[str] = []

    def get(self, attr_name: str, default: str = "") -> str:
        """Lấy giá trị của một thuộc tính HTML."""
        return self.attrs.get(attr_name.lower(), default)

    def get_text(self, separator: str = " ") -> str:
        """Lấy toàn bộ nội dung text của node và các node con."""
        parts: list[str] = []
        if self.text_parts:
            parts.extend(self.text_parts)
        for child in self.children:
            child_text = child.get_text(separator=separator)
            if child_text:
                parts.append(child_text)
        return separator.join(parts).strip()

    def find_all(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
        attr_has: tuple[str, str] | None = None,
        predicate: Callable[["DOMNode"], bool] | None = None,
    ) -> list["DOMNode"]:
        """Tìm tất cả các node con thỏa mãn tiêu chí tìm kiếm."""
        results: list[DOMNode] = []
        match = True

        if tag and self.tag != tag.lower():
            match = False

        if class_contains:
            cls = self.attrs.get("class", "")
            if class_contains.lower() not in cls.lower():
                match = False

        if attr_has:
            k, v = attr_has
            attr_val = self.attrs.get(k.lower(), "")
            if v.lower() not in attr_val.lower():
                match = False

        if predicate and not predicate(self):
            match = False

        if match and (tag or class_contains or attr_has or predicate):
            results.append(self)

        for child in self.children:
            results.extend(child.find_all(tag, class_contains, attr_has, predicate))

        return results

    def find(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
        attr_has: tuple[str, str] | None = None,
        predicate: Callable[["DOMNode"], bool] | None = None,
    ) -> "DOMNode | None":
        """Tìm node con đầu tiên thỏa mãn tiêu chí tìm kiếm."""
        res = self.find_all(tag, class_contains, attr_has, predicate)
        return res[0] if res else None

    def find_parent(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
    ) -> "DOMNode | None":
        """Tìm node cha gần nhất thỏa mãn điều kiện."""
        curr = self.parent
        while curr is not None:
            match = True
            if tag and curr.tag != tag.lower():
                match = False
            if class_contains:
                cls = curr.attrs.get("class", "")
                if class_contains.lower() not in cls.lower():
                    match = False
            if match:
                return curr
            curr = curr.parent
        return None


class DOMTreeBuilder(HTMLParser):
    """Xây dựng cây DOMNode từ chuỗi HTML sử dụng thư viện chuẩn của Python."""

    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr",
        "img", "input", "link", "meta", "param",
        "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.root = DOMNode("root", [])
        self.current = self.root

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = DOMNode(tag, attrs, parent=self.current)
        self.current.children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.VOID_TAGS:
            return
        curr = self.current
        while curr.parent is not None:
            if curr.tag == tag.lower():
                self.current = curr.parent
                break
            curr = curr.parent

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.current.text_parts.append(cleaned)

    @classmethod
    def parse(cls, html: str) -> DOMNode:
        """Hàm tiện ích phân tích nhanh chuỗi HTML thành DOMNode gốc."""
        builder = cls()
        builder.feed(html or "")
        return builder.root
