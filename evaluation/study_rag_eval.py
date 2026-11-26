"""Study-document RAG evaluation: standard vs agentic retrieval, with and without the embedding model.

Usage (project root):   python -m evaluation.study_rag_eval
Outputs:                docs/assignment/evaluation/study_rag_results.json and STUDY_RAG_EVAL.md

* No database and no network: three fictional study documents are built as a real PDF and real DOCX files and go
  through the production pipeline (study_documents.extract -> chunk_units -> study_qa / doc_agent).
* Ground truth: for every question, the document and page/section that hold the answer and the words a correct
  answer must contain. Unanswerable questions check the honest "not found" behaviour.
* Metrics per configuration: hit@1, recall@k, precision@k, strict citation precision and citation hit,
  answer correctness, failure rate,
  no-answer accuracy, hallucination rate (answers given to unanswerable questions), follow-up consistency,
  multi-document recall, mean / p95 latency and CPU time per question.
"""

from __future__ import annotations

import io
import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from docx import Document  # noqa: E402

from backend.services import embeddings, study_documents, study_qa  # noqa: E402
from backend.services.assistant import doc_agent  # noqa: E402
from resume_factory import make_pdf  # noqa: E402

OUT = ROOT / "docs" / "assignment" / "evaluation"

# ------------------------------------------------------------------
# Fictional study material (written for this evaluation)
# ------------------------------------------------------------------

DBMS = [  # PDF, one list per page
    ["Relational Databases",
     "A relational database stores data in tables made of rows and columns.",
     "A primary key uniquely identifies each row in a table and cannot be null.",
     "A foreign key references the primary key of another table and keeps related data consistent."],
    ["Normalization",
     "Normalization organizes tables to reduce redundancy and update anomalies.",
     "First normal form requires atomic values and no repeating groups.",
     "Second normal form removes partial dependencies on part of a composite key.",
     "Third normal form removes transitive dependencies between non-key columns."],
    ["Indexes",
     "An index is a data structure that speeds up lookups on a column.",
     "Indexes cost extra storage and make inserts and updates slower.",
     "A B-tree index keeps keys sorted, so range queries are efficient.",
     "A hash index is fast for equality lookups but cannot serve range queries."],
    ["Transactions",
     "A transaction groups statements so that they all succeed or all fail together.",
     "ACID stands for atomicity, consistency, isolation and durability.",
     "Durability means committed changes survive a crash because they are written to the log.",
     "Isolation levels such as read committed and serializable control what concurrent transactions see."],
    ["SQL Queries",
     "A JOIN combines rows from two tables using a related column.",
     "An inner join keeps only rows that match in both tables, while a left join keeps every row of the left table.",
     "GROUP BY aggregates rows into groups, and HAVING filters the aggregated groups.",
     "A subquery is a query nested inside another query."],
]
OOP = {  # DOCX: heading -> paragraphs
    "Encapsulation": ["Encapsulation bundles data with the methods that use it and hides internal state behind a public interface.",
                      "Private fields with getters and setters are a common way to apply encapsulation."],
    "Inheritance": ["Inheritance lets a subclass reuse and extend the behaviour of a parent class.",
                    "Deep inheritance hierarchies make code harder to change, so composition is often preferred."],
    "Polymorphism": ["Polymorphism lets one interface work with objects of different types.",
                     "Method overriding is runtime polymorphism, while method overloading is resolved at compile time."],
    "Abstraction": ["Abstraction shows only the essential features of an object and hides implementation details.",
                    "Abstract classes and interfaces are the main tools for abstraction in Java."],
    "SOLID principles": ["The single responsibility principle says a class should have only one reason to change.",
                         "The open closed principle says classes should be open for extension but closed for modification.",
                         "The dependency inversion principle says high-level modules should depend on abstractions."],
}
OS_NOTES = [  # PDF
    ["Processes and Threads",
     "A process is a running program with its own memory space.",
     "A thread is the smallest unit of execution and threads of one process share memory.",
     "A context switch saves the state of one process and restores another."],
    ["CPU Scheduling",
     "Round robin scheduling gives each process a fixed time quantum in turn.",
     "Shortest job first minimises average waiting time but can starve long jobs.",
     "Priority scheduling can cause starvation, which aging prevents by raising the priority of waiting processes."],
    ["Deadlocks",
     "A deadlock happens when processes wait forever for resources held by each other.",
     "The four conditions for deadlock are mutual exclusion, hold and wait, no preemption and circular wait.",
     "The banker's algorithm avoids deadlock by checking that resource allocation keeps the system in a safe state."],
    ["Memory Management",
     "Paging divides memory into fixed-size frames and processes into pages of the same size.",
     "A page fault occurs when a program accesses a page that is not in main memory.",
     "Virtual memory lets programs use more memory than is physically installed by keeping pages on disk."],
]

# Distractor documents for the hard setting: overlapping vocabulary (index, transaction, process, key, class)
# in a different sense, so retrieval must pick the right meaning and document.
DISTRACTORS = {
    "networking.pdf": [
        ["Network Basics", "A network transaction in banking systems is a message exchanged between two servers.",
         "A switch forwards frames by MAC address inside a local network.", "A router forwards packets between networks by IP address."],
        ["Transport Layer", "TCP provides reliable ordered delivery with a three-way handshake.",
         "UDP is connectionless and is used for streaming and DNS.", "A port number identifies a process on a host."],
        ["Security", "A public key encrypts data that only the matching private key can decrypt.",
         "TLS protects data in transit between a browser and a server.", "A firewall filters traffic by rules on ports and addresses."],
    ],
    "ml_notes.pdf": [
        ["Supervised Learning", "A classification model predicts a class label for each example.",
         "The training set is used to fit the model and the test set to evaluate it.",
         "Overfitting happens when a model memorises the training data and fails on new data."],
        ["Evaluation", "Precision is the share of predicted positives that are correct.",
         "Recall is the share of actual positives that the model finds.", "Cross-validation repeats training on different folds of the data."],
        ["Arrays and Indexing", "An array index starts at zero in Python and NumPy.",
         "Negative indexing reads elements from the end of a list.", "Slicing selects a range of elements with start and stop positions."],
    ],
}

# (question, [(document name, page or section)], words the answer must contain, kind)
QUESTIONS = [
    ("What does ACID stand for?", [("dbms.pdf", 4)], ["atomicity", "durability"], "fact"),
    ("What is a primary key?", [("dbms.pdf", 1)], ["uniquely"], "fact"),
    ("What does third normal form remove?", [("dbms.pdf", 2)], ["transitive"], "fact"),
    ("What are the costs of using an index?", [("dbms.pdf", 3)], ["storage"], "fact"),
    ("Which index type is good for range queries?", [("dbms.pdf", 3)], ["b-tree"], "fact"),
    ("What does HAVING do?", [("dbms.pdf", 5)], ["aggregated"], "fact"),
    ("How do committed changes survive a crash?", [("dbms.pdf", 4)], ["log"], "paraphrase"),
    ("How can I make lookups on a column faster?", [("dbms.pdf", 3)], ["index"], "paraphrase"),
    ("Which join keeps every row of the left table?", [("dbms.pdf", 5)], ["left join"], "fact"),
    ("What is encapsulation?", [("oop.docx", "Encapsulation")], ["bundles"], "fact"),
    ("What is the difference between overriding and overloading?", [("oop.docx", "Polymorphism")], ["runtime", "compile"], "fact"),
    ("Why is composition often preferred over inheritance?", [("oop.docx", "Inheritance")], ["harder to change"], "paraphrase"),
    ("What does the single responsibility principle say?", [("oop.docx", "SOLID principles")], ["one reason"], "fact"),
    ("Which tools does Java offer for abstraction?", [("oop.docx", "Abstraction")], ["interfaces"], "fact"),
    ("How does a subclass reuse code from its parent?", [("oop.docx", "Inheritance")], ["inheritance"], "paraphrase"),
    ("What is a thread?", [("os.pdf", 1)], ["smallest unit"], "fact"),
    ("What are the four conditions for deadlock?", [("os.pdf", 3)], ["circular wait"], "fact"),
    ("How does aging prevent starvation?", [("os.pdf", 2)], ["raising the priority"], "fact"),
    ("What happens when a program accesses a page that is not in memory?", [("os.pdf", 4)], ["page fault"], "paraphrase"),
    ("How can programs use more memory than is installed?", [("os.pdf", 4)], ["virtual memory"], "paraphrase"),
    ("What is a foreign key and what does third normal form remove?", [("dbms.pdf", 1), ("dbms.pdf", 2)], ["references", "transitive"], "multi"),
    ("Compare encapsulation and abstraction", [("oop.docx", "Encapsulation"), ("oop.docx", "Abstraction")], ["bundles", "essential"], "multi"),
    ("What is a deadlock and how does round robin scheduling work?", [("os.pdf", 3), ("os.pdf", 2)], ["wait forever", "time quantum"], "multi"),
    ("What does ACID stand for and what is polymorphism?", [("dbms.pdf", 4), ("oop.docx", "Polymorphism")], ["atomicity", "one interface"], "cross"),
    ("What is a process and what is a primary key?", [("os.pdf", 1), ("dbms.pdf", 1)], ["running program", "uniquely"], "cross"),
    ("Who won the football world cup in 2018?", [], [], "no_answer"),
    ("What is the capital of Australia?", [], [], "no_answer"),
    ("How do I bake sourdough bread?", [], [], "no_answer"),
    ("What is the boiling point of water on Mars?", [], [], "no_answer"),
    ("Which Kubernetes command scales a deployment?", [], [], "no_answer"),
]
# (first question, follow-up, location the follow-up should still cite)
FOLLOWUPS = [
    ("What is an index?", "Explain that in more detail", ("dbms.pdf", 3)),
    ("What is polymorphism?", "Give me an example of it", ("oop.docx", "Polymorphism")),
    ("What is a deadlock?", "Why does it happen?", ("os.pdf", 3)),
]


def build_library(chunk_chars=None, overlap=None, distractors=False):
    files = {"dbms.pdf": make_pdf([[(50, 750 - 16 * i, t) for i, t in enumerate(p)] for p in DBMS]),
             "os.pdf": make_pdf([[(50, 750 - 16 * i, t) for i, t in enumerate(p)] for p in OS_NOTES])}
    if distractors:
        for name, pages in DISTRACTORS.items():
            files[name] = make_pdf([[(50, 750 - 16 * i, t) for i, t in enumerate(p)] for p in pages])
    document = Document()
    for heading, paragraphs in OOP.items():
        document.add_heading(heading, level=1)
        for text in paragraphs:
            document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    files["oop.docx"] = buffer.getvalue()
    docs = []
    for number, (name, data) in enumerate(files.items(), start=1):
        extraction = study_documents.extract(name.rsplit(".", 1)[1], data)
        doc = SimpleNamespace(document_id=number, filename=name, chunks=[])
        for c in study_documents.chunk_units(extraction.units, chunk_chars, overlap):
            doc.chunks.append(SimpleNamespace(document_id=number, document=doc, position=c["position"], page=c["page"],
                                              section=c["section"], text=c["text"]))
        doc.chunk_count = len(doc.chunks)
        docs.append(doc)
    return study_qa.Library(docs)


def relevant(chunk, wanted) -> bool:
    return any(chunk.document.filename == name and (chunk.page == where or chunk.section == where) for name, where in wanted)


def evaluate(library, mode: str, k: int = 4) -> dict:
    rows, latencies, cpu = [], [], []
    for question, wanted, words, kind in QUESTIONS:
        t0, c0 = time.perf_counter(), time.process_time()
        if mode == "agentic" or (mode == "auto" and study_qa.wants_agentic(question)):
            hits, _, _ = study_qa.retrieve_agentic(library, question, k)
            hits = hits[:k] if kind not in ("multi", "cross") else hits
        else:
            hits, _ = study_qa.retrieve(library, question, k)
        answer = study_qa.answer(library, question, mode)
        latencies.append((time.perf_counter() - t0) * 1000)
        cpu.append((time.process_time() - c0) * 1000)
        text = " ".join(p.text for p in answer.points).lower()
        cited = [p.chunk for p in answer.points]
        row = {"question": question, "kind": kind, "found": answer.found}
        if kind == "no_answer":
            row.update(no_answer_ok=not answer.found)
        else:
            rel = [h for h in hits if relevant(h.chunk, wanted)]
            locations = {(h.chunk.document.filename, h.chunk.page or h.chunk.section) for h in rel}
            row.update(hit1=bool(hits) and relevant(hits[0].chunk, wanted),
                       recall=len(locations) / len(wanted),
                       precision=len(rel) / len(hits) if hits else 0.0,
                       citation_precision=(sum(relevant(c, wanted) for c in cited) / len(cited)) if cited else 0.0,
                       citation_hit=any(relevant(c, wanted) for c in cited),
                       answer_ok=answer.found and all(w in text for w in words))
        rows.append(row)
    follow = []
    for first, second, wanted in FOLLOWUPS:
        reply = doc_agent.reply(library, second, None, previous=first, mode=mode)
        follow.append(any(f"{wanted[0]}" in s["label"] and str(wanted[1]) in s["label"] for s in reply.sources))
    answerable = [r for r in rows if r["kind"] != "no_answer"]
    unanswerable = [r for r in rows if r["kind"] == "no_answer"]
    multi = [r for r in rows if r["kind"] in ("multi", "cross")]
    mean = lambda xs: round(statistics.mean(xs), 3) if xs else None  # noqa: E731
    return {
        "mode": mode,
        "questions": len(rows),
        "hit_at_1": mean([float(r["hit1"]) for r in answerable]),
        "k": k,
        "recall_at_k": mean([r["recall"] for r in answerable]),
        "precision_at_k": mean([r["precision"] for r in answerable]),
        "citation_precision": mean([r["citation_precision"] for r in answerable]),
        "citation_hit": mean([float(r["citation_hit"]) for r in answerable]),
        "answer_correctness": mean([float(r["answer_ok"]) for r in answerable]),
        "multi_part_recall": mean([r["recall"] for r in multi]),
        "multi_part_answer_correctness": mean([float(r["answer_ok"]) for r in multi]),
        "no_answer_accuracy": mean([float(r["no_answer_ok"]) for r in unanswerable]),
        "hallucination_rate": mean([float(not r["no_answer_ok"]) for r in unanswerable]),
        "followup_consistency": mean([float(x) for x in follow]),
        "latency_ms_mean": round(statistics.mean(latencies), 1),
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1),
        "cpu_ms_mean": round(statistics.mean(cpu), 1),
        "failure_rate": round((sum(not r["answer_ok"] for r in answerable)
                               + sum(not r["no_answer_ok"] for r in unanswerable)) / len(rows), 3),
        "failures": [r["question"] for r in answerable if not r["answer_ok"]] + [r["question"] for r in unanswerable if not r["no_answer_ok"]],
    }


SETTINGS = [
    {"name": "standard set", "chunk_chars": None, "overlap": None, "distractors": False, "k": 4},
    {"name": "hard set (2 distractor documents, 220-character chunks, k=2)", "chunk_chars": 220, "overlap": 40,
     "distractors": True, "k": 2},
]


def main() -> None:
    results = {"configurations": [], "settings": []}
    try:
        embeddings.get_embedder()
        semantic = True
    except embeddings.EmbeddingError:
        semantic = False
    configs = [("hybrid (BM25 + MiniLM)", None)] if semantic else []
    configs.append(("keyword only (BM25)", "keyword"))
    for setting in SETTINGS:
        library = build_library(setting["chunk_chars"], setting["overlap"], setting["distractors"])
        size, overlap = study_documents.chunk_settings()
        results["settings"].append({"name": setting["name"], "k": setting["k"],
                                    "chunk_chars": setting["chunk_chars"] or size, "overlap": setting["overlap"] if setting["overlap"] is not None else overlap,
                                    "documents": [{"name": d.filename, "chunks": d.chunk_count} for d in library.documents]})
        for label, flag in configs:
            if flag == "keyword":
                embeddings.set_embedder(_Unavailable())
            study_qa._cache.clear()
            for mode in ("standard", "agentic", "auto"):
                evaluate(library, mode, setting["k"])               # warm-up (model load, vectors)
                outcome = evaluate(library, mode, setting["k"])
                outcome["retrieval"], outcome["setting"] = label, setting["name"]
                results["configurations"].append(outcome)
                print(f"{setting['name'][:9]:9} {label:24} {mode:9} hit@1={outcome['hit_at_1']} recall@k={outcome['recall_at_k']} "
                      f"answer={outcome['answer_correctness']} multi={outcome['multi_part_recall']}/{outcome['multi_part_answer_correctness']} "
                      f"no-answer={outcome['no_answer_accuracy']} follow-up={outcome['followup_consistency']} "
                      f"latency={outcome['latency_ms_mean']}ms")
            embeddings.set_embedder(None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "study_rag_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["# Study-document RAG evaluation", "",
             f"{len(QUESTIONS)} questions ({sum(q[3] == 'no_answer' for q in QUESTIONS)} unanswerable, "
             f"{sum(q[3] in ('multi', 'cross') for q in QUESTIONS)} multi-part / cross-document) + {len(FOLLOWUPS)} follow-ups, "
             "on fictional study notes built as real PDF/DOCX files and run through the production pipeline.", ""]
    for st in results["settings"]:
        lines.append(f"- **{st['name']}**: {st['chunk_chars']}-character chunks, {st['overlap']} overlap, top-{st['k']}; documents "
                     + ", ".join(f"{d['name']} ({d['chunks']} passages)" for d in st["documents"]))
    lines += ["", "| Setting | Retrieval | Mode | hit@1 | recall@k | precision@k | citation precision / hit | answers | failure rate | multi-part recall / answers | no-answer | hallucination | follow-up | latency mean / p95 (ms) | CPU (ms) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results["configurations"]:
        lines.append(f"| {r['setting'].split(' (')[0]} | {r['retrieval']} | {r['mode']} | {r['hit_at_1']} | {r['recall_at_k']} | {r['precision_at_k']} | "
                     f"{r['citation_precision']} / {r['citation_hit']} | {r['answer_correctness']} | {r['failure_rate']} | {r['multi_part_recall']} / {r['multi_part_answer_correctness']} | "
                     f"{r['no_answer_accuracy']} | {r['hallucination_rate']} | {r['followup_consistency']} | {r['latency_ms_mean']} / {r['latency_ms_p95']} | {r['cpu_ms_mean']} |")
    lines += ["", "Failures per configuration:", ""]
    for r in results["configurations"]:
        lines.append(f"- {r['setting'].split(' (')[0]} / {r['retrieval']} / {r['mode']}: {', '.join(r['failures']) or 'none'}")
    lines += ["", METHOD.rstrip("\n")]           # the file ends with exactly one newline
    (OUT / "STUDY_RAG_EVAL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written", OUT / "STUDY_RAG_EVAL.md")


METHOD = """## Methodology

- **Modes.** *standard*: one hybrid retrieval (BM25 + MiniLM cosine 0.5/0.5, rerank, dedupe). *agentic*: the question is
  split into parts ("?", ";", "also", "as well as", "and what/how/…", "compare X and Y", "X vs Y"), each part is retrieved separately, a part with a weak result is retried once with the best passage's heading terms, results
  are merged round-robin. *auto* (production default): agentic only when `wants_agentic()` sees several parts.
- **Retrieval metrics** (answerable questions; k = top-k of the setting): hit@1 = the first passage is from a labelled
  page/section; recall@k = labelled locations found / labelled locations; precision@k = relevant passages / passages
  returned (agentic may return more than k for multi-part questions).
- **Citation precision (strict)** = share of the passages *quoted in the final answer* that come from a labelled
  page/section; **citation hit** = at least one quoted passage is from a labelled location.
- **Answer correctness** = an answer was given and contains every required key word for that question.
  **Failure rate** = (wrong answerable answers + unanswerable questions that got an answer) / all questions.
- **No-answer accuracy / hallucination rate**: the 5 unanswerable questions must return "not found".
- **Follow-up consistency**: the follow-up's sources still point at the expected document and page.
- **Latency / CPU**: wall-clock and process CPU per question for retrieval + answer building, after one warm-up pass,
  in one Python process on this laptop's CPU. Optional AI rewording is not included (it adds 15-60 s on CPU with Ollama).

## Limitations

- Small, hand-labelled dataset (30 questions + 3 follow-ups) on fictional notes written for this test; results show
  relative differences between modes, not accuracy on real student material.
- Answer correctness is a key-word check, not a human judgement of answer quality.
- Labels are page/section level; a relevant sentence in an unlabelled passage counts as wrong (strict).
- Latency depends on machine load; compare modes within one run only. Windows' process CPU timer has ~15 ms
  resolution, so CPU values below ~15 ms are approximate.
- The extractive answers quote sentences; the evaluation does not measure the optional AI-reworded answers.
"""


class _Unavailable:
    def embed(self, texts):
        raise embeddings.EmbeddingError("disabled for the keyword-only run")


if __name__ == "__main__":
    main()
