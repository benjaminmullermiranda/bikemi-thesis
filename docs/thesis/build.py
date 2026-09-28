"""Regenerate docs/thesis/thesis_full.md from the numbered chapter files.

The chapters are canonical; thesis_full.md is a build artefact (project
convention, docs/handoff.md §6). Doing the merge by hand is how the two drifted
before, so it is a script now. Also reports the word count the programme's
guidelines are checked against: 4,000-6,000 words for a quantitative thesis,
excluding the appendix.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["00_front_matter.md", "01_introduction.md", "02_related_work.md",
         "03_data_case_study.md", "04_methodology.md", "05_results.md",
         "06_references.md", "07_appendix.md"]
OUT = HERE / "thesis_full.md"


def words(text):
    """Body words only: HTML comments, markdown table rows, and headings are
    excluded, matching the guidelines' 'tables and figures excluded'."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith(("|", "#")))
    return len(text.split())


def main():
    parts, abstract_total, chapters_total, main_refs_total, appendix_total = [], 0, 0, 0, 0
    for name in ORDER:
        body = (HERE / name).read_text(encoding="utf-8").rstrip()
        n = words(body)
        if name == "00_front_matter.md":
            abstract = body.split("## Abstract", 1)[1].split("**AI use statement.**", 1)[0]
            abstract_total = words(abstract)
        elif name == "07_appendix.md":
            appendix_total = n
        else:
            main_refs_total += n
            if name not in ("00_front_matter.md", "06_references.md"):
                chapters_total += n
        print(f"  {name:<28} {n:>5} words")
        parts.append(body)
    OUT.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    print(f"  {'abstract':<28} {abstract_total:>5} words")
    print(f"  {'chapters 1–5':<28} {chapters_total:>5} words")
    print(f"  {'chapters 1–5 + references':<28} {main_refs_total:>5} words")
    print(f"  {'appendix (excluded)':<28} {appendix_total:>5} words")
    print("  quantitative: 4,000–6,000 excl. appendix")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
