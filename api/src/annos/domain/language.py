"""Choosing which of the three names to show.

Storage is language-neutral: `name_fi`, `name_sv` and `name_en` are peers, and
search covers all three whatever the user's preference — a Finnish speaker still
types "banana" sometimes, and a label photo may only ever have produced a
Swedish name.

Presentation is where a language gets picked, and it is picked here rather than
in either adapter, so the two surfaces cannot disagree about it.
"""

from annos.models import LANGUAGES

DEFAULT = "fi"


def resolve(names: dict[str, str | None], preferred: str) -> tuple[str | None, str | None]:
    """Return (name, the language it actually came from).

    Falls back through the remaining languages rather than returning nothing: a
    Swedish name is more use to an English-preferring reader than a blank. The
    second element says which language was served, so a client is never left
    guessing why a name looks unfamiliar.
    """
    for language in (preferred, *LANGUAGES):
        name = names.get(language)
        if name:
            return name, language
    return None, None
