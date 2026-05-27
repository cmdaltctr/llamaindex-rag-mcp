# Exp 6 — Ground-Truth Queries (Human-Readable)

24 queries total. The companion machine-readable file is `ground-truth.json`.

| Category         | Count |
| ---------------- | ----- |
| Heading-targeted | 12    |
| General          | 8     |
| Cross-domain     | 4     |
| **Total**        | **24**|

## Heading-targeted (12)

These queries name the heading explicitly. The new chunker should beat the
`SentenceSplitter`-only baseline by at least 5 pp on Hit@1 here.

1. Under Getting Started in the Nuxt readme, what command creates a new starter project?
   → `nuxt-readme.md` § Getting Started → "npm create nuxt@latest"
2. In the Vue Development section of the Nuxt readme, what helper sets the page title?
   → `nuxt-readme.md` § Vue Development → "useSeoMeta"
3. Under Professional Support in the Nuxt readme, who handles technical audit and consulting?
   → `nuxt-readme.md` § Professional Support → "Nuxt Experts"
4. Under Option Stores in the Pinia docs, what shape does the state factory return?
   → `pinia-core-concepts.md` § Option Stores → "count: 0"
5. In the Setup Stores section of Pinia, what does a ref become inside the store?
   → `pinia-core-concepts.md` § Setup Stores → "state properties"
6. Under Destructuring from a Store in Pinia, which helper preserves reactivity?
   → `pinia-core-concepts.md` § Destructuring from a Store → "storeToRefs"
7. In the Pinia "What syntax should I pick" section, what does the doc recommend?
   → `pinia-core-concepts.md` § What syntax should I pick? → "pick the one you feel the most comfortable"
8. Under Project setup in the Django REST quickstart, how do you create a virtual environment?
   → `django-rest-quickstart.md` § Project setup → "python3 -m venv"
9. In the Serializers section of the Django REST quickstart, what serializer class is used?
   → `django-rest-quickstart.md` § Serializers → "HyperlinkedModelSerializer"
10. Under Views in the Django REST quickstart, what base class do the viewsets inherit from?
    → `django-rest-quickstart.md` § Views → "viewsets.ModelViewSet"
11. In the Pagination section of the Django REST quickstart, what page size is configured?
    → `django-rest-quickstart.md` § Pagination → "PAGE_SIZE"
12. Under URLs in the Django REST quickstart, what router class is used to wire the API?
    → `django-rest-quickstart.md` § URLs → "DefaultRouter"

## General (8)

These queries don't reference a specific heading. The new chunker must hold
Hit@1 within ±2 pp of the baseline. The prose / edge files are exercised here.

13. What features does Nuxt provide for full-stack web applications?
    → `nuxt-readme.md` § Nuxt (intro) → "Server-side rendering"
14. How does Pinia define a store and what is the unique id for?
    → `pinia-core-concepts.md` § Defining a Store → "defineStore"
15. Why does the RAG essay argue hybrid retrieval is the obvious response?
    → `essay-on-rag.md` (prose) → "Run a sparse retriever and a dense retriever in parallel"
16. What does the prose essay say about deleting code as an engineering skill?
    → `no-headings.md` (edge, no headings at all) → "Delete aggressively"
17. How does the Django REST quickstart create the initial admin user?
    → `django-rest-quickstart.md` § Project setup → "createsuperuser"
18. What does the RAG essay say a cross-encoder reranker actually computes?
    → `essay-on-rag.md` (prose) → "transformer that takes the query and the candidate chunk together"
19. What does the prose essay say about choosing a programming language for production?
    → `no-headings.md` (edge) → "Programming languages do not matter as much as people think"
20. What benefits does the Nuxt readme list for SEO and meta tags?
    → `nuxt-readme.md` § Nuxt (intro) → "Search engine optimization"

## Cross-domain / negative (4)

These queries should match exactly one source. The other structured docs MUST NOT rank above it.

21. How do I require authenticated users on a REST framework viewset?
    → `django-rest-quickstart.md` § Views → "permissions.IsAuthenticated"
    must NOT match: `nuxt-readme.md`, `pinia-core-concepts.md`
22. How do auto-imports work for composables and components in Nuxt?
    → `nuxt-readme.md` § Nuxt (intro) → "Auto imports of components"
    must NOT match: `pinia-core-concepts.md`, `django-rest-quickstart.md`
23. Should I define each Pinia store in a different file?
    → `pinia-core-concepts.md` § Using the store → "different file"
    must NOT match: `nuxt-readme.md`, `django-rest-quickstart.md`
24. What does the RAG essay say a cross-encoder reranker computes per candidate?
    → `essay-on-rag.md` (prose) → "forward pass"
    must NOT match: `nuxt-readme.md`, `pinia-core-concepts.md`,
    `django-rest-quickstart.md`, `no-headings.md`

## Notes

- All 12 heading-targeted queries name the heading either by exact phrase
  ("Getting Started", "Option Stores", "Destructuring from a Store") or close
  paraphrase. With the Markdown chunker active, the gold chunk should carry
  that heading in its metadata.
- General queries 16 and 19 target `no-headings.md`, which has no Markdown
  headings at all. The Markdown branch must still produce non-empty chunks
  for this file (Tier 2 task 1.7) — these queries verify that.
- General queries 15, 18 target `essay-on-rag.md` (prose-heavy with one H1).
- Cross-domain queries 21–24 verify the chunker doesn't hurt cross-document
  precision when the query genuinely belongs to one source. Q21 targets
  Django REST, Q22 targets Nuxt, Q23 targets Pinia, Q24 targets the prose
  essay — one query per structured/prose source so a chunker regression
  in any one of them surfaces here.
