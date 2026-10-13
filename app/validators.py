import re

_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.I)


def clean_link(link: str | None) -> str | None:
    """Banner links may be a page of the site or an http(s) address, never javascript: and similar."""
    if link is None:
        return None
    link = link.strip()
    if not link:
        return None
    if _SCHEME.match(link) and not link.lower().startswith(("http://", "https://")):
        raise ValueError("The link must be a page of the store or start with http:// or https://")
    return link
