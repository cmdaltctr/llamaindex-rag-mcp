# torch.nn.LayerNorm — implementation notes

`torch.nn.LayerNorm` applies layer normalisation over the last `D` dimensions
of an input tensor, where `D = len(normalized_shape)`. Unlike batch
normalisation, `torch.nn.LayerNorm` computes the mean and variance per sample
across the normalised dimensions, which makes it independent of batch size and
well suited to autoregressive models and variable-length sequences.

## Constructor

```python
torch.nn.LayerNorm(
    normalized_shape,
    eps: float = 1e-5,
    elementwise_affine: bool = True,
    bias: bool = True,
    device=None,
    dtype=None,
)
```

- `normalized_shape` may be an int or a tuple. If an int, it is treated as a
  single-dimensional shape — the last axis is normalised.
- `elementwise_affine=True` adds learnable per-element gain (`weight`) and
  bias parameters of shape `normalized_shape`.
- `bias=False` disables only the learnable bias (PyTorch ≥ 1.9).
- `eps` is added to the variance before taking the square root for numerical
  stability. The default `1e-5` is rarely worth changing.

## Common pitfalls with `torch.nn.LayerNorm`

1. **Dimension confusion.** `torch.nn.LayerNorm(d_model)` normalises the last
   axis. If your tensor is `(B, T, d_model)`, this is what transformers want.
   If your tensor is `(B, d_model, T)`, you need to permute first or use a
   different module.
2. **GroupNorm versus LayerNorm.** `torch.nn.GroupNorm(1, C)` is mathematically
   equivalent to `torch.nn.LayerNorm(C)` over `(B, C, *)` inputs, and is what
   you want for image features.
3. **Half precision.** `torch.nn.LayerNorm` is sensitive to fp16 underflow at
   small tensor scales; bf16 is safer. PyTorch 2.1+ ships an opt-in
   `LayerNormKernelImpl` that handles this internally.
4. **RMSNorm versus LayerNorm.** Modern transformers (Llama, Mistral, Qwen)
   replace `torch.nn.LayerNorm` with `RMSNorm`, which drops the mean
   subtraction. Do not mix them — switching from `torch.nn.LayerNorm` to
   `RMSNorm` mid-training will diverge.

## Numerical example

```python
import torch

x = torch.tensor([[1.0, 2.0, 3.0, 4.0]])
ln = torch.nn.LayerNorm(4, elementwise_affine=False)
y = ln(x)
# Mean ≈ 0, std ≈ 1 along the last axis.
```
