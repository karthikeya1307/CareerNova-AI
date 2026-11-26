# Study-document RAG evaluation

30 questions (5 unanswerable, 5 multi-part / cross-document) + 3 follow-ups, on fictional study notes built as real PDF/DOCX files and run through the production pipeline.

- **standard set**: 1000-character chunks, 150 overlap, top-4; documents dbms.pdf (5 passages), os.pdf (4 passages), oop.docx (5 passages)
- **hard set (2 distractor documents, 220-character chunks, k=2)**: 220-character chunks, 40 overlap, top-2; documents dbms.pdf (11 passages), os.pdf (8 passages), networking.pdf (4 passages), ml_notes.pdf (4 passages), oop.docx (6 passages)

| Setting | Retrieval | Mode | hit@1 | recall@k | precision@k | citation precision / hit | answers | failure rate | multi-part recall / answers | no-answer | hallucination | follow-up | latency mean / p95 (ms) | CPU (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| standard set | hybrid (BM25 + MiniLM) | standard | 1.0 | 1.0 | 0.62 | 0.992 / 1.0 | 0.96 | 0.033 | 1.0 / 0.8 | 1.0 | 0.0 | 1.0 | 12.1 / 13.1 | 92.7 |
| standard set | hybrid (BM25 + MiniLM) | agentic | 1.0 | 1.0 | 0.62 | 0.703 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 17.9 / 33.8 | 141.1 |
| standard set | hybrid (BM25 + MiniLM) | auto | 1.0 | 1.0 | 0.62 | 0.935 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 15.9 / 33.7 | 128.1 |
| standard set | keyword only (BM25) | standard | 1.0 | 1.0 | 0.763 | 1.0 / 1.0 | 0.92 | 0.067 | 1.0 / 0.6 | 1.0 | 0.0 | 1.0 | 0.9 / 1.0 | 8.3 |
| standard set | keyword only (BM25) | agentic | 1.0 | 1.0 | 0.763 | 0.809 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 1.5 / 3.4 | 12.0 |
| standard set | keyword only (BM25) | auto | 1.0 | 1.0 | 0.763 | 0.951 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 1.1 / 2.2 | 1.0 |
| hard set | hybrid (BM25 + MiniLM) | standard | 1.0 | 0.98 | 0.88 | 1.0 / 1.0 | 0.96 | 0.033 | 0.9 / 0.8 | 1.0 | 0.0 | 1.0 | 12.2 / 13.4 | 95.3 |
| hard set | hybrid (BM25 + MiniLM) | agentic | 1.0 | 1.0 | 0.867 | 0.745 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 18.2 / 32.3 | 148.4 |
| hard set | hybrid (BM25 + MiniLM) | auto | 1.0 | 1.0 | 0.867 | 0.957 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 15.6 / 33.8 | 120.8 |
| hard set | keyword only (BM25) | standard | 1.0 | 0.96 | 0.94 | 0.992 / 1.0 | 0.92 | 0.067 | 0.8 / 0.6 | 1.0 | 0.0 | 1.0 | 1.6 / 2.1 | 12.5 |
| hard set | keyword only (BM25) | agentic | 1.0 | 1.0 | 0.927 | 0.825 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 1.7 / 3.1 | 5.2 |
| hard set | keyword only (BM25) | auto | 1.0 | 1.0 | 0.927 | 0.946 / 1.0 | 1.0 | 0.0 | 1.0 / 1.0 | 1.0 | 0.0 | 1.0 | 1.5 / 3.1 | 1.0 |

Failures per configuration:

- standard set / hybrid (BM25 + MiniLM) / standard: What is a foreign key and what does third normal form remove?
- standard set / hybrid (BM25 + MiniLM) / agentic: none
- standard set / hybrid (BM25 + MiniLM) / auto: none
- standard set / keyword only (BM25) / standard: What is a foreign key and what does third normal form remove?, What is a deadlock and how does round robin scheduling work?
- standard set / keyword only (BM25) / agentic: none
- standard set / keyword only (BM25) / auto: none
- hard set / hybrid (BM25 + MiniLM) / standard: What is a foreign key and what does third normal form remove?
- hard set / hybrid (BM25 + MiniLM) / agentic: none
- hard set / hybrid (BM25 + MiniLM) / auto: none
- hard set / keyword only (BM25) / standard: What is a foreign key and what does third normal form remove?, What is a deadlock and how does round robin scheduling work?
- hard set / keyword only (BM25) / agentic: none
- hard set / keyword only (BM25) / auto: none

## Methodology

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
