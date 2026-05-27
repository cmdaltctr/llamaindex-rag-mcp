# numpy.fft.rfft2 quick reference

`numpy.fft.rfft2(a, s=None, axes=(-2, -1), norm=None)` computes the
two-dimensional discrete Fourier transform of a **real** input array. Because
the input is real, the output is Hermitian-symmetric and `numpy.fft.rfft2`
returns only the non-redundant half along the last transformed axis, saving
roughly half the storage versus `numpy.fft.fft2`.

## How `numpy.fft.rfft2` differs from `fft2`

| Aspect              | `numpy.fft.fft2`                  | `numpy.fft.rfft2`                          |
| ------------------- | --------------------------------- | ------------------------------------------ |
| Input dtype         | complex (real is auto-cast)       | real-input only                            |
| Output shape last   | `n` (full)                        | `n // 2 + 1` (one-sided)                   |
| Inverse             | `numpy.fft.ifft2`                 | `numpy.fft.irfft2`                         |
| Memory              | full complex                      | ~half                                      |
| Speed (typical)     | baseline                          | 1.3–1.7× faster on large real arrays       |

The asymmetry on the **last** axis is the part that catches new users out.
If you call `numpy.fft.rfft2` on a 1024 × 1024 real array, the output is
1024 × 513 complex, not 1024 × 1024. The first axis is full-length; only the
last axis is folded.

## When to use `numpy.fft.rfft2`

Use `numpy.fft.rfft2` whenever you know the input is real and you do not
specifically need the redundant negative-frequency half. The most common cases:

- Image processing (real-valued pixel data).
- Spectral analysis of real-valued sensor signals on a 2D grid.
- Convolution via the convolution theorem when both operands are real.

Pair it with `numpy.fft.irfft2` for the round-trip. Passing the output of
`numpy.fft.rfft2` into `numpy.fft.ifft2` will give you a complex result with a
small imaginary part where there should be zero — that is the most common
`numpy.fft.rfft2` bug in production code.

## Code

```python
import numpy as np

img = np.random.rand(512, 512)
spectrum = np.fft.rfft2(img)
assert spectrum.shape == (512, 257)

restored = np.fft.irfft2(spectrum, s=img.shape)
assert np.allclose(restored, img, atol=1e-10)
```
