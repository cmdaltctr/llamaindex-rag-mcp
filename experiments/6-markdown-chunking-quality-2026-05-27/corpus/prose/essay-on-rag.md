# Why retrieval augmentation still matters

Large language models trained on the open web know a lot about a lot of things, but they
do not know your code, your customer database, your private wiki, or yesterday's
production incident. They never will, and that is fine. The interesting question has
never been "can the model memorise everything"; it has always been "how do we put the
right paragraph in front of the model at the right moment so it can do something useful
with it?". Retrieval-augmented generation, or RAG, is one of the more honest answers we
have to that question, and it is also one of the most under-rated.

The original sin of the early RAG era was treating retrieval as a solved problem. Drop
your documents into a vector store, embed the query, do a cosine similarity, hand the
top five chunks to the model, and call it done. People built whole product companies on
exactly that pipeline, and the pipeline mostly worked, until it did not. The failure
modes were the same ones any information retrieval researcher from the 1990s would have
predicted. Rare-term queries failed, because dense embeddings smear word identity into
a soup of nearby concepts. Long documents failed, because chunk boundaries cut sentences
in half and the model received fragments. Multi-hop questions failed, because the gold
chunk was three chunks away from the chunk that scored highest, and nobody bothered to
expand the retrieval window. None of these problems were new. The vector-database
revolution had quietly forgotten everything BM25 had taught us about lexical matching.

Hybrid retrieval is the obvious response, and it is now widespread enough that nobody
publishes papers about it any more, which is usually a sign that an idea has won. Run
a sparse retriever and a dense retriever in parallel. Fuse the rankings with reciprocal
rank fusion. Hand the union to a cross-encoder reranker for the final shortlist. The
sparse retriever finds the documents that contain your exact identifier; the dense
retriever finds the documents that talk about the same thing using different words; the
reranker resolves disagreements between the two. The whole thing fits in a few hundred
lines of Python and adds maybe forty milliseconds of latency. There is no good reason
to ship a production RAG system without it, and yet most pipelines still do not, because
vector databases come with a tutorial that ends at "do a cosine similarity" and most
teams never get past the tutorial.

Reranking deserves its own paragraph. A cross-encoder is just a transformer that takes
the query and the candidate chunk together as a single sequence, runs them through the
full attention stack, and emits a relevance score. It is computationally heavier than
a bi-encoder by a couple of orders of magnitude, which is why nobody runs it over the
full corpus. But running it over the top fifty candidates from a cheaper retriever is
almost free, and the quality lift is dramatic. A cross-encoder can tell the difference
between "the paper discusses X in passing" and "the paper is about X", a distinction
that bi-encoders smear because they encode the query and the document in isolation and
lose all of the cross-attention information that would normally let them weigh the
importance of each token in context. The cost is one forward pass per candidate, which
on a small distilled model is somewhere around one to five milliseconds.

Chunking is where most teams quietly lose the plot. The default in every framework is
to split documents into fixed-size windows of, say, 512 tokens with a 64-token overlap,
and this default is wrong for almost every real corpus. Markdown documents have
headings, code blocks, tables, and lists that should never be split mid-element. Legal
documents have section numbers and citations that should travel together. Source code
has function boundaries, class definitions, and import blocks. PDFs have pages and
columns and footnotes. Treating all of these as a single stream of tokens and slicing
every 512 of them is a sin against the structure of the source material. The fix is to
do a structural pass first — split the Markdown by headings, the code by functions, the
legal text by sections — and only fall back to fixed-size windows when a structural
unit exceeds the size cap. This is exactly what every serious RAG implementation does,
and it is also what most quick-start guides skip over, because it is more code.

Embeddings are commoditising fast, but the tail still matters. The frontier
general-purpose models — the Nomic, Qwen, BGE, and E5 families — are now within a
percentage point or two of each other on most benchmarks, and the differences come down
to the long tail of edge cases. Domain-specific embeddings still win on domain-specific
corpora; a model fine-tuned on biomedical literature will beat a generalist on a
biomedical retrieval task by enough percentage points to justify the operational
overhead of running two models. Multilingual coverage matters if your corpus is not
English; almost every benchmark is English-only, and an embedding that is great on
English MTEB can be merely adequate on Malay or Arabic. And dimensionality matters less
than people think — the move from 768 to 1024 to 1536 dimensions buys you small
constant-factor improvements, but it costs you proportional storage, and at scale the
storage cost dominates the recall improvement.

Evaluation is the thing nobody wants to do, and the thing without which none of the
rest matters. Write your queries by hand, before you build anything. Pre-record the
gold chunk for each query, so the eval is mechanical. Hold out a set of queries that
you never tune against. Measure Hit at 1, Hit at 5, MRR, and Recall at 10, partitioned
by query category — heading-targeted versus general, rare-term versus semantic, short
versus long. Run the evaluation every time you change a parameter. If your evaluation
takes more than a minute to run end-to-end, you will not run it, and your numbers will
drift. The best RAG system in your organisation is the one with the best evaluation
harness, not the one with the cleverest retrieval architecture, because the cleverest
retrieval architecture cannot survive a year of changes without one.

The thing that keeps me up at night is that retrieval will eventually become a model
capability rather than a pipeline component. The current generation of frontier models
can already do passable retrieval over their context window using attention alone; the
next generation will probably do passable retrieval over a much larger context window
using sparse attention, retrieval-augmented attention, or some architecture we have not
invented yet. When that happens, the carefully tuned BM25 and reranker pipelines we are
building today will look like the early-2000s search-engine plumbing that nobody runs
any more. I do not think that day is close, and I think the pipeline approach has at
least another five good years in it. But it is worth holding lightly. The pipeline
wins until it does not.
