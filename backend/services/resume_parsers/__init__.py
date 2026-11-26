"""Three resume-parsing approaches with one output schema (see ``common.ParsedResume``):

* ``regex_parser``  - rules and regular expressions only;
* ``llm_parser``    - structured extraction with the configured AI provider;
* ``hybrid_parser`` - both, reconciled against the resume text.

The default resume upload keeps using ``backend.services.resume_parser`` (unchanged contract); these parsers are
available for comparison through ``POST /resumes/parse-preview``, ``GET /resumes/{id}/parse-preview`` and
``python -m backend.manage parse-resume``. None of them stores anything.
"""

from backend.services.resume_parsers.common import ParsedResume, ResumeFileError

PARSERS = ("regex", "llm", "hybrid")


def run(name: str, file_bytes: bytes, filename: str, provider=None) -> ParsedResume:
    from backend.services.resume_parsers import hybrid_parser, llm_parser, regex_parser

    if name == "regex":
        return regex_parser.parse(file_bytes, filename)
    if name == "llm":
        return llm_parser.parse(file_bytes, filename, provider)
    if name == "hybrid":
        return hybrid_parser.parse(file_bytes, filename, provider)
    raise ValueError(f"Unknown parser {name!r}; choose one of {', '.join(PARSERS)}.")


__all__ = ["PARSERS", "ParsedResume", "ResumeFileError", "run"]
