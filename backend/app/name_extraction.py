"""Extracts director/officer names from 8-K Item 5.02 filing text using Claude.

EDGAR's structured data only tells us THAT a filing discloses a management
change (Item 5.02) - the actual name(s) only exist in the filing's prose, so
this is a text-extraction problem rather than a structured-data lookup.
"""

from bs4 import BeautifulSoup

from .config import get_settings

_MAX_CHARS = 15000  # keeps token usage bounded; 5.02 disclosures are near the top of the document

_TOOL = {
    "name": "record_people",
    "description": (
        "Record every director or officer named in this SEC 8-K filing as newly "
        "appointed/elected, or as departing/resigning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The person's full name"},
                        "title": {
                            "type": "string",
                            "description": "Their role/title, if the filing states one (empty string if not stated)",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["appointed", "departed", "other"],
                            "description": "Whether they were newly appointed/elected, or departed/resigned",
                        },
                    },
                    "required": ["name", "action"],
                },
            }
        },
        "required": ["people"],
    },
}

_SYSTEM_PROMPT = (
    "You extract structured data from SEC 8-K filings that disclose Item 5.02 "
    "(departure/election of directors or officers). Read the filing text and call "
    "the record_people tool with every person named as newly appointed/elected or "
    "as departing/resigning, along with their title if stated. Do not include "
    "people mentioned only in passing (e.g. signatories, unrelated board members). "
    "If no such person is clearly named, call the tool with an empty list."
)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _format_people(people: list[dict]) -> str:
    """Only newly appointed/elected people are shown - this column is titled
    "New director(s)/officer(s)", so departures are deliberately excluded."""
    parts = []
    for person in people:
        if person.get("action") != "appointed":
            continue
        name = person.get("name", "").strip()
        if not name:
            continue
        title = (person.get("title") or "").strip()
        label = f"{name} ({title})" if title else name
        parts.append(label)
    return "; ".join(parts)


class PeopleExtractor:
    def __init__(self) -> None:
        import anthropic  # deferred: only needed when this feature is actually used

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in backend/.env - required to run app.extract_people"
            )
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def extract(self, filing_text: str) -> str:
        """Returns a display-ready string, e.g. 'Jane Doe (CFO); John Smith (Director) [departed]'.
        Returns "" if no names were found."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_people"},
            messages=[{"role": "user", "content": filing_text[:_MAX_CHARS]}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_people":
                return _format_people(block.input.get("people", []))
        return ""
