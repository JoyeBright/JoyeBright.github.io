---
classes: wide
title:  "Transformers – Input Handling"
notion_url: https://j-pourmostafa.notion.site/transformers-input-handling
categories:
  - Learning Notes
tags:
  - Transformers
  - NLP
  - LLMs
---

# Transformers – Input Handling

ℹ️ 

I've drafted a quick, simple blog post on transformers. This post is part 1 of a series I'm putting together. It will give you a rundown of what transformers are and explain input handling—specifically, tokenization and positional encoding.

Please note that I wrote this quickly so that it may contain errors and typos. Feel free to drop me a line if you find any. Thanks!

</aside>

## 🦂 What are Transformers?

A transformer is a neural network architecture for sequence-to-sequence and sequence-to-label tasks (e.g., translation, summarization, classification, etc), which replaces recurrence or convolution with an attention mechanism. 

### What is the core idea in Transformers?

While typical RNNs process tokens strictly from left to right with a hidden state, a Transformer allows each token to directly look at (i.e., attend to) other tokens and build a context-aware representation.

## 🚂 Architecture

A transformer architecture consists of: 

- Encoder stack (understanding input)
- Decoder stack (generating output)

Each stack has two big sub-blocks:

1. **(Multi-head) self-attention**
    - tokens exchange information (“who should I pay attention to?”)
2. **(Position-wise) feed-forward neural network** **(FFN/MLP)**
    - Each token is processed independently by the same small neural net (“now that I have context, transform me”)

Therefore, self-attention allows interaction among tokens (n-to-n), thereby providing contextualization. Then, the MLP refines that information per token.

On top of these two sub-blocks, there are two important parts: **Residual connections** (skip connections) and **layer normalization**.

## 🪓 Tokenization

Transformer never deals with characters directly. It only sees token IDs. Text to tokens (words/subwords/bytes).

<aside>

```bash
"unbelievable" → ["un", "believ", "able"] → [417, 9821, 211]
```

</aside>

## 📐 Input/Token Embeddings

Each token ID from the previous step (tokenization) is mapped to a dense vector using an embedding matrix.

### What does the embedding matrix actually look like?

It’s just a simple lookup table.

$$
E = |vocabulary-size| * |model-dimension|
$$

Vocabulary size refers to the number of unique tokens—for example, subword tokenization methods like BPE or SentencePiece typically use 32,000, 50,000, or 100,000 tokens.

Model dimension is the size of each embedding vector. For example, the original Transformer used 512 dimensions. All these features are learnable—gradients flow back to E and update the values during training. Note that E contains real numbers (floats).

## 🗺️ Positional Encoding (PE)

Word order matters in text—it changes both meaning and/or fluency. Transformers lack an inherent sense of order because self-attention is order-agnostic and treats inputs as a set rather than a sequence. To address this, positional encoding injects sequence information, which allows the attention mechanism to reason about token positions.

Positional encoding addresses this by adding position information to each token. However, we can't simply use a single number as an index. The attention mechanism expects vectors, not scalars, so we can't just add the embedding (token) + i, where i is the token’s position, because scalars don’t encode relationships on their own.

### Example of Sinusoidal PE

Instead of simply telling the self-attention that `position = 3` (which we cannot do in practice), Sinusoidal PE says position 3 is a pattern made of waves.

**Model dimension**: `d_model = 3`

**Sentence**:

```
"Transformers are beast"
```

**Positions:** 

```
Transformers => position 1
are => position 2
beast => position 3
```

Let’s assume from the input embedding step, we’ve got 3-dimensional vectors:

| Word | Token embedding |
| --- | --- |
| Transformers | [0.6, 0.2, 0.5] |
| are | [0.1, 0.7, 0.3] |
| beast | [0.8, 0.4, 0.1] |

At this point, there is no order. We define:

| Dimension | Encoding |
| --- | --- |
| dim 0 | sin(pos) |
| dim 1 | cos(pos) |
| dim 2 | sin(pos / 100) |

You may wonder why the encoding of dimension 0 is `sin(pos)`. This follows directly from the sinusoidal positional encoding formula. For dimension 0, the frequency index is `k = 0`, which gives

$$
PE(pos, 0) = \sin\left(\frac{pos}{10000^{0}}\right) = \sin(pos)
$$

As `k` increases across dimensions, the denominator grows, producing sine and cosine waves at different scales, which allows positional information to be encoded at multiple resolutions.

Then, we compute the positional encoding. For example, for position 1, the encoding is:

```notion
p₁ = [
  sin(1),
  cos(1),
  sin(0.01)
]
≈ [0.84, 0.54, 0.01]
```

We calculate the PE for the other positions and then add it to the embedding vectors. For example, for position 1:

```notion
e₁ = [0.6, 0.2, 0.5]
p₁ = [0.84, 0.54, 0.01]
-------------------------
x₁ = [1.44, 0.74, 0.51]
```
