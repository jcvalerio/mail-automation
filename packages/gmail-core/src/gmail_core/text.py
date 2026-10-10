import html
import re

ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff]")


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = ZERO_WIDTH_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()
