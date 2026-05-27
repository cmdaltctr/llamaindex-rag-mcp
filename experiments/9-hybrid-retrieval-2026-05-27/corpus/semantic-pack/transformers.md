# Self-attention as a building block

The self-attention layer is the central computational unit of the modern
sequence-modelling stack introduced by Vaswani and colleagues in 2017. It
replaces the recurrent connections of LSTM and GRU encoders with a parallel
operation: every token in the input sequence attends to every other token
through a learned softmax over scaled dot products of query, key, and value
projections.

Because the operation is a single matrix multiplication followed by a
softmax, all positions are computed simultaneously rather than one step at a
time. This is what makes self-attention fast on modern accelerators and what
lets the same layer model relationships between tokens that are far apart in
the input — there is no sequential bottleneck between distant positions.

Multi-head self-attention runs several attention computations in parallel
with different linear projections. Each head can specialise on a different
kind of relationship — syntactic agreement, coreference, positional structure
— and the heads are concatenated and projected back to the model dimension at
the output of the layer.

Position information is supplied externally through sinusoidal or learned
positional embeddings, and more recently through rotary embeddings (RoPE) or
relative-position biases (ALiBi). The point is that self-attention itself is
permutation-invariant; the position information must be added to the input
for the layer to behave the way we want.

The cost is quadratic in sequence length: an n-token sequence requires
O(n²) attention scores per head per layer. Several variants — sparse
attention, sliding-window attention, linear attention, FlashAttention —
address the quadratic cost without abandoning the parallelism that made
the original layer attractive.
