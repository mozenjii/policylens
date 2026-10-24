# policylens

Question answering over public healthcare coverage policies that cites the exact passage behind each claim, and says "not supported" when it can't.

> **Status:** early. I'm at the design stage and there is no released code yet. The results table below stays empty until a script in this repo produces the numbers.

## The problem

Coverage policies are long, organised around criteria and billing codes, refer to each other, and change over time. A generic RAG demo returns passages that sound relevant, writes a fluent answer and cites nothing you can check. When it's wrong you can't tell whether retrieval missed the passage or the model misread it.

## What it will do

- Parse policies into sections and individual criteria, so a citation points at a specific criterion and not a page.
- Answer by pulling verbatim supporting quotes first and writing the answer only from those quotes. No supporting quote means no answer.
- Look codes (HCPCS, ICD-10) up in an exact index instead of relying on embeddings.
- Answer "as of" a date, using the policy version that was in force then.
- For every failure, say which stage failed: retrieval, generation or citation.

## How I plan to know it works

A hand-checked question set with gold passages, covering single-hop questions, multi-hop questions across policies, code lookups, date-dependent questions, negations, and questions the corpus can't answer.

| Measurement | How | Result |
|---|---|---|
| Retrieval recall at k and MRR | Gold supporting passages | not measured |
| Citation precision and recall | Answers against gold passages | not measured |
| Risk-coverage curve and abstention accuracy | Unanswerable questions included | not measured |
| Hybrid vs dense-only vs graph-assisted | Ablation, with a multi-hop subset | not measured |

## Design notes

**Quote first, then answer.** Generating an answer and then hunting for a citation invites made-up support. Extracting the quotes first makes the citation structural, and a deterministic check can confirm each quote really appears in the cited passage.

**One accuracy number hides the interesting part.** A system that abstains more is safer and less useful. I'll report risk-coverage curves, so you can see accuracy at each level of "how often does it answer".

**Codes aren't semantic.** Embeddings are poor at telling `J1745` from `J1746`. Code questions go to an exact lookup and merge with the semantic results.

**Policies have versions.** Retrieval takes an as-of date and a jurisdiction, and the question set includes cases where the answer changed.

**Data.** I won't redistribute policy text. The repo will fetch it from the source and keep only derived metadata until I've confirmed the licence terms.

## Roadmap

- [ ] Fetch, parse and chunk policies with provenance
- [ ] Question set and retrieval evaluation
- [ ] Hybrid retrieval and reranking
- [ ] Quote-first answers with abstention
- [ ] Failure attribution and ablations (including graph-assisted retrieval)
- [ ] Write-up

## Related projects

Part of a set of six projects about building LLM systems you can trust:
[evalgate](https://github.com/mozenjii/evalgate),
[policylens](https://github.com/mozenjii/policylens),
[docproof](https://github.com/mozenjii/docproof),
[tollgate](https://github.com/mozenjii/tollgate),
[redline](https://github.com/mozenjii/redline),
[casefile](https://github.com/mozenjii/casefile).

Built by Mohib Ahmad.
