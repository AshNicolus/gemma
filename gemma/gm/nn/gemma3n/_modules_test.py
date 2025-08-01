# Copyright 2025 DeepMind Technologies Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for transformer modules."""

import logging

from gemma.gm.nn.gemma3n import _config
from gemma.gm.nn.gemma3n import _modules
import jax
import jax.numpy as jnp
import numpy as np
import pytest


jax.config.update('jax_threefry_partitionable', False)

_ATTN_TYPE = _modules.AttentionType.GLOBAL
_NANO_ATTN_TYPE = _modules.AttentionType.GLOBAL


def test_embedder_encode():
  vocab_size = 10
  embed_dim = 4
  embedder = _modules.Embedder(vocab_size=vocab_size, embed_dim=embed_dim)
  embedding_matrix = jnp.ones((vocab_size, embed_dim))
  params = {'params': {'input_embedding': embedding_matrix}}

  # Test with flat array (batch size 1).
  tokens = jnp.array([2, 3])
  output = embedder.apply(params, tokens, method=_modules.Embedder.encode)
  expected = jnp.ones((len(tokens), embed_dim)) * 2.0
  np.testing.assert_array_equal(output, jnp.array(expected))

  # Test with batch.
  tokens = jnp.array([[2, 3, 4], [5, 6, 7]])
  output = embedder.apply(params, tokens, method=_modules.Embedder.encode)
  expected = jnp.ones((tokens.shape[0], tokens.shape[1], embed_dim)) * 2.0
  np.testing.assert_array_equal(output, jnp.array(expected))


def test_embedder_decode():
  vocab_size = 5
  embed_dim = 2
  embedder = _modules.Embedder(vocab_size=vocab_size, embed_dim=embed_dim)
  embedding_matrix = jnp.ones((vocab_size, embed_dim))
  params = {'params': {'input_embedding': embedding_matrix}}

  # Test with flat array (batch size 1).
  vector = jnp.array([1, 2])
  output = embedder.apply(params, vector, method=_modules.Embedder.decode)
  expected = jnp.ones(vocab_size) * 3.0
  np.testing.assert_array_equal(output, jnp.array(expected))

  # Test with batch.
  vectors = jnp.array([[1, 2], [3, 4], [5, 6]])
  output = embedder.apply(params, vectors, method=_modules.Embedder.decode)
  expected = (
      jnp.ones((vectors.shape[0], vocab_size))
      * jnp.array([3.0, 7.0, 11.0])[:, None]
  )
  np.testing.assert_array_equal(output, jnp.array(expected))


# TODO(mblondel): Add tests for `encode_vision` here.


def test_create_sliding_mask_decode_none_rotated_cache_pos():
  cache_len = 4
  end_index = 1
  segment_pos = jnp.array([[1]])

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=1
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[[False, True, False, False]]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=2
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[[True, True, True, False]]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=3
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[[True, True, True, True]]],
  )


def test_kv_cache_sharing_patterns():

  kv_cache_sharing_config = _config.KVCacheSharingConfig(
      frac_shared_layers=5.0 / 10.0,
      share_global=True,
      share_local=True,
  )
  num_layers = 10
  attention_types = [
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.GLOBAL,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.LOCAL_SLIDING,
      _modules.AttentionType.GLOBAL,
  ]
  kv_cache_sharing_patterns = _config.create_kv_cache_sharing_patterns(
      kv_cache_sharing_config, num_layers, attention_types
  )
  assert kv_cache_sharing_patterns == [0, 1, 2, 3, 4, 3, 3, 3, 3, 4]

  layer_names = []
  for i in range(num_layers):
    if (
        kv_cache_sharing_config is not None
        and kv_cache_sharing_patterns is not None
    ):
      layer_name = f'layer_{kv_cache_sharing_patterns[i]}'
    else:
      layer_name = f'layer_{i}'
    layer_names.append(layer_name)
  assert layer_names == [
      'layer_0',
      'layer_1',
      'layer_2',
      'layer_3',
      'layer_4',
      'layer_3',
      'layer_3',
      'layer_3',
      'layer_3',
      'layer_4',
  ]


def test_create_sliding_mask_decode_rotated_cache_pos():
  cache_len = 4
  end_index = 5
  segment_pos = jnp.array([[5]])

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=1
  )
  np.testing.assert_array_equal(
      sliding_mask,
      # cache_positions = [
      #   4,      5,     2,     3,
      # ]
      [[[False, True, False, False]]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=2
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[[True, True, False, False]]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=3
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[[True, True, False, True]]],
  )


def test_create_sliding_mask_prefill_rotated_cache_pos():
  cache_len = 4
  end_index = 5
  segment_pos = jnp.array([[5, 6]])

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=1
  )
  np.testing.assert_array_equal(
      sliding_mask,
      # cache_positions = [
      #   4,      5,     6,     3,
      # ]
      [[
          [False, True, False, False],
          [False, False, True, False],
      ]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=2
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[
          [True, True, True, False],
          [False, True, True, False],
      ]],
  )

  sliding_mask = _modules._create_sliding_mask(
      segment_pos, end_index, cache_len, sliding_window_size=3
  )
  np.testing.assert_array_equal(
      sliding_mask,
      [[
          [True, True, True, True],
          [True, True, True, False],
      ]],
  )


def _get_attn_output(
    batch_size: int,
    seq_len: int,
    num_heads: int,
    head_dim: int,
    features: int,
    cache_size: int,
    query_pre_attn_scalar: float | None = None,
    num_kv_heads: int | None = None,
) -> tuple[jnp.ndarray, jnp.ndarray]:

  if query_pre_attn_scalar is None:
    query_pre_attn_scalar = head_dim**-0.5

  if num_kv_heads is None:
    # num_kv_heads is only different from num_heads in the GQA case.
    num_kv_heads = num_heads

  attn = _modules.Attention(
      num_heads=num_heads,
      num_kv_heads=num_kv_heads,
      features=features,
      head_dim=head_dim,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
  )

  rng = jax.random.PRNGKey(0)
  x = jnp.ones((batch_size, seq_len, features))
  segment_pos = (
      jnp.repeat(jnp.arange(seq_len), batch_size).reshape(seq_len, batch_size).T
  )
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_kv_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )
  attn_mask = jnp.ones((batch_size, seq_len, cache_size))

  params = attn.init(rng, x, segment_pos, cache, attn_mask)
  cache, output = attn.apply(params, x, segment_pos, cache, attn_mask)

  return cache, output


def test_attention():
  batch_size = 5
  num_heads = 2
  head_dim = 4
  features = 8
  cache_size = 7
  seq_len = 6

  cache, output = _get_attn_output(
      batch_size=batch_size,
      seq_len=seq_len,
      num_heads=num_heads,
      head_dim=head_dim,
      features=features,
      cache_size=cache_size,
  )

  expected_cache_shape = (batch_size, cache_size, num_heads, 4)
  expected_output_shape = (batch_size, seq_len, features)
  assert cache['k'].shape == expected_cache_shape
  assert cache['v'].shape == expected_cache_shape
  assert output.shape == expected_output_shape


def test_attention_with_gqa():
  batch_size = 5
  num_heads = 8
  head_dim = 2
  features = 10
  cache_size = 7
  num_kv_heads = 4
  seq_len = 6

  cache, output = _get_attn_output(
      batch_size=batch_size,
      seq_len=seq_len,
      num_heads=num_heads,
      head_dim=head_dim,
      features=features,
      num_kv_heads=num_kv_heads,
      cache_size=cache_size,
  )

  expected_cache_shape = (batch_size, cache_size, num_kv_heads, head_dim)
  expected_output_shape = (batch_size, seq_len, features)
  assert cache['k'].shape == expected_cache_shape
  assert cache['v'].shape == expected_cache_shape
  assert output.shape == expected_output_shape


def test_sliding_window():
  num_heads = 2
  head_dim = 4
  features = 8
  cache_size = 7
  batch_size = 2
  query_pre_attn_scalar = head_dim**-0.5
  seq_len = 6

  attn = _modules.Attention(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      features=features,
      head_dim=head_dim,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
  )

  rng = jax.random.PRNGKey(0)
  x = jnp.ones((batch_size, seq_len, features))
  segment_pos = (
      jnp.repeat(jnp.arange(seq_len), batch_size).reshape(seq_len, batch_size).T
  )
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )
  attn_mask = jnp.ones((batch_size, seq_len, cache_size))

  params = attn.init(rng, x, segment_pos, cache, attn_mask)
  _, output = attn.apply(params, x, segment_pos, cache, attn_mask)

  sliding_attn = _modules.Attention(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      features=features,
      head_dim=head_dim,
      attn_type=_modules.AttentionType.LOCAL_SLIDING,
      sliding_window_size=2,
      query_pre_attn_scalar=query_pre_attn_scalar,
  )
  _, sliding_output = sliding_attn.apply(
      params, x, segment_pos, cache, attn_mask
  )

  assert not (output == sliding_output).all()


def test_query_pre_attn_scalar_modifies_output():
  num_heads = 2
  head_dim = 4
  features = 8
  batch_size = 2
  cache_size = 3
  seq_len = 1

  query_pre_attn_scalar_by_embed_dim_div_num_heads: float = (
      features // num_heads
  )
  query_pre_attn_scalar_by_head_dim: float = head_dim**-0.5
  _, output_by_head_dim = _get_attn_output(
      batch_size,
      seq_len,
      num_heads,
      head_dim,
      features,
      cache_size,
      query_pre_attn_scalar=query_pre_attn_scalar_by_head_dim,
  )
  _, output_by_embed_dim_div_num_heads = _get_attn_output(
      batch_size,
      seq_len,
      num_heads,
      head_dim,
      features,
      cache_size,
      query_pre_attn_scalar=query_pre_attn_scalar_by_embed_dim_div_num_heads,
  )


@pytest.mark.parametrize(
    'transpose_gating_einsum',
    [
        False,
        True,
    ],
)
def test_ffw(transpose_gating_einsum: bool):
  features = 4
  hidden_dim = 3
  batch_size = 5
  seq_len = 1

  inputs = jnp.arange(seq_len, batch_size + 1)[:, None, None]
  inputs = jnp.repeat(inputs, features, axis=-1)

  ffw = _modules.FeedForward(
      features=features,
      hidden_dim=hidden_dim,
      transpose_gating_einsum=transpose_gating_einsum,
  )

  params = {'linear': jnp.ones((hidden_dim, features))}

  # Different checkpoints have params saved in different order
  if transpose_gating_einsum:
    params['gating_einsum'] = jnp.ones((2, hidden_dim, features))
  else:
    params['gating_einsum'] = jnp.ones((2, features, hidden_dim))

  outputs = ffw.apply({'params': params}, inputs)

  expected_shape = (batch_size, seq_len, features)
  assert outputs.shape == expected_shape


@pytest.mark.parametrize(
    'transpose_gating_einsum, expected_grad',
    [
        (False, [-1.916515e-04, -5.391428e-05, -2.923766e-04]),
        (True, [1.574128e-05, -1.301362e-04, -1.037612e-04]),
    ],
)
def test_ffw_grad(transpose_gating_einsum: bool, expected_grad: list[float]):
  features = 2
  hidden_dim = 3
  batch_size = 2
  inputs = jnp.arange(1, batch_size + 1)[:, None, None]
  inputs = jnp.repeat(inputs, features, axis=-1)
  ffw = _modules.FeedForward(
      features=features,
      hidden_dim=hidden_dim,
      transpose_gating_einsum=transpose_gating_einsum,
  )
  loss = lambda params, inputs: jnp.square(
      ffw.apply(params, inputs) - jnp.ones((batch_size, 1, features))
  ).mean()

  params = ffw.init(jax.random.PRNGKey(0), inputs)

  grad_loss = jax.grad(loss)
  grad = grad_loss(params, inputs)


@pytest.mark.parametrize(
    'num_altup_inputs',
    [
        4,
        1,
    ],
)
def test_altup(num_altup_inputs: int):
  features = 4
  batch_size = 5
  seq_len = 1

  x = jnp.ones((batch_size, seq_len, features))
  inputs = [jnp.copy(x) for _ in range(num_altup_inputs)]

  altup = _modules.AltUp(
      d_model=features,
      num_altup_inputs=num_altup_inputs,
  )
  params = altup.init(jax.random.PRNGKey(0), inputs, x)
  outputs = altup.apply(params, inputs, x)
  np.testing.assert_equal(len(outputs), num_altup_inputs)
  expected_shape = (batch_size, seq_len, features)
  np.testing.assert_array_equal(outputs[0].shape, expected_shape)

  predict_outputs = altup.apply(params, inputs, method=altup.predict)
  np.testing.assert_equal(len(predict_outputs), num_altup_inputs)

  correct_outputs = altup.apply(params, predict_outputs, x,
                                method=altup.correct)
  np.testing.assert_equal(len(correct_outputs), num_altup_inputs)
  np.testing.assert_array_equal(correct_outputs[0].shape, expected_shape)


def test_block():
  num_heads = 2
  embed_dim = 4
  head_dim = 6
  cache_size = 3
  batch_size = 5
  seq_len = 1

  inputs = jnp.ones((batch_size, seq_len, embed_dim))
  positions = jnp.zeros((batch_size, seq_len))

  # Initialize cache.
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )

  # Check that initial cache shape is correct.
  expected_cache_shape = (batch_size, cache_size, num_heads, head_dim)
  assert cache['k'].shape == expected_cache_shape
  assert cache['v'].shape == expected_cache_shape

  # Initialize and apply the block.
  block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=1,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=head_dim**-0.5,
      transpose_gating_einsum=False,
  )

  attn_mask = jnp.ones((batch_size, seq_len, cache_size))
  params = block.init(
      jax.random.PRNGKey(0), inputs, positions, cache, attn_mask
  )

  new_cache, outputs = block.apply(params, inputs, positions, cache, attn_mask)

  # Check that updated cache shape is correct.
  assert new_cache['k'].shape == expected_cache_shape
  assert new_cache['v'].shape == expected_cache_shape
  assert new_cache['end_index'].shape == (batch_size,)

  # Check that output shape is correct.
  expected_output_shape = (batch_size, seq_len, embed_dim)
  assert outputs.shape == expected_output_shape


def test_post_attention_norm_modifies_output():
  num_heads = 1
  embed_dim = 1
  head_dim = 2
  hidden_dim = 1
  cache_size = 1
  batch_size = 1
  query_pre_attn_scalar = head_dim**-0.5
  inputs = jnp.ones((batch_size, 1, embed_dim))
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )
  attn_mask = jnp.ones((batch_size, 1, cache_size))
  normed_block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=hidden_dim,
      use_post_attn_norm=True,
      use_post_ffw_norm=False,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
      transpose_gating_einsum=False,
  )
  unnormed_block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=hidden_dim,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
      transpose_gating_einsum=False,
  )

  all_outputs = []
  for block in (normed_block, unnormed_block):
    params = block.init(
        jax.random.PRNGKey(0), inputs, jnp.array([[0]]), cache, attn_mask
    )

    _, outputs = block.apply(params, inputs, jnp.array([[0]]), cache, attn_mask)
    all_outputs.append(outputs)

  normed_output, unnormed_output = all_outputs  # pylint: disable=unbalanced-tuple-unpacking
  logging.info('normed_output: %s', normed_output)
  logging.info('unnormed_output: %s', unnormed_output)

  # Normed and unnormed outputs should not be equal.
  with np.testing.assert_raises(AssertionError):
    np.testing.assert_array_almost_equal(normed_output, unnormed_output)


def test_post_ffw_norm_modifies_output():
  num_heads = 1
  embed_dim = 1
  head_dim = 2
  hidden_dim = 1
  cache_size = 1
  batch_size = 1
  query_pre_attn_scalar = head_dim**-0.5
  inputs = jnp.ones((batch_size, 1, embed_dim))
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )
  attn_mask = jnp.ones((batch_size, 1, cache_size))
  normed_block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=hidden_dim,
      use_post_attn_norm=False,
      use_post_ffw_norm=True,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
      transpose_gating_einsum=False,
  )
  unnormed_block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=hidden_dim,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=query_pre_attn_scalar,
      transpose_gating_einsum=False,
  )

  all_outputs = []
  for block in (normed_block, unnormed_block):

    params = block.init(
        jax.random.PRNGKey(0), inputs, jnp.array([[0]]), cache, attn_mask
    )

    # Replace mlp block params with 1s as ffw will initialize with
    # 0s which will not properly test normalization.
    for param in ['gating_einsum', 'linear']:
      params['params']['mlp'][param] = jnp.ones_like(
          params['params']['mlp'][param]
      )

    _, outputs = block.apply(params, inputs, jnp.array([[0]]), cache, attn_mask)
    all_outputs.append(outputs)

  normed_output, unnormed_output = all_outputs  # pylint: disable=unbalanced-tuple-unpacking
  logging.info('normed_output: %s', normed_output)
  logging.info('unnormed_output: %s', unnormed_output)

  # Normed and unnormed outputs should not be equal.
  with np.testing.assert_raises(AssertionError):
    np.testing.assert_array_almost_equal(normed_output, unnormed_output)


def test_block_with_altup():
  num_heads = 2
  embed_dim = 4
  head_dim = 6
  cache_size = 3
  batch_size = 5
  seq_len = 1
  num_altup_inputs = 4

  inputs = jnp.ones((batch_size, seq_len, embed_dim))
  positions = jnp.zeros((batch_size, seq_len))

  # Initialize cache.
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )

  # Check that initial cache shape is correct.
  expected_cache_shape = (batch_size, cache_size, num_heads, head_dim)
  np.testing.assert_array_equal(cache['k'].shape, expected_cache_shape)
  np.testing.assert_array_equal(cache['v'].shape, expected_cache_shape)

  # Initialize and apply the block.
  block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=1,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_NANO_ATTN_TYPE,
      query_pre_attn_scalar=head_dim**-0.5,
      transpose_gating_einsum=False,
      use_altup=True,
      num_altup_inputs=num_altup_inputs,
  )

  inputs = [jnp.copy(inputs) for _ in range(num_altup_inputs)]
  attn_mask = jnp.ones((batch_size, seq_len, cache_size))
  params = block.init(
      jax.random.PRNGKey(0), inputs, positions, cache, attn_mask
  )

  new_cache, outputs = block.apply(
      params, inputs, positions, cache, attn_mask
  )

  # Check that updated cache shape is correct.
  np.testing.assert_array_equal(new_cache['k'].shape, expected_cache_shape)
  np.testing.assert_array_equal(new_cache['v'].shape, expected_cache_shape)
  np.testing.assert_array_equal(new_cache['end_index'].shape, (batch_size,))

  # Check that output shape is correct.
  expected_output_shape = (batch_size, seq_len, embed_dim)
  np.testing.assert_equal(len(outputs), num_altup_inputs)
  np.testing.assert_array_equal(outputs[0].shape, expected_output_shape)


def test_laurel_module():
  d_model = 4
  rank = 2
  batch_size = 5
  seq_len = 3
  inputs = jnp.ones((batch_size, seq_len, d_model))

  laurel = _modules.Laurel(d_model=d_model, rank=rank)
  params = laurel.init(jax.random.PRNGKey(0), inputs)
  outputs = laurel.apply(params, inputs)

  # Test that the shape matches.
  expected_shape = (batch_size, seq_len, d_model)
  np.testing.assert_array_equal(outputs.shape, expected_shape)

  # Test that the output is correct.
  linear_left = params['params']['linear_left']['w']
  linear_right = params['params']['linear_right']['w']
  computed_outputs = jnp.einsum('btd,dr->btr', inputs, linear_left)
  computed_outputs = jnp.einsum('btr,rd->btd', computed_outputs, linear_right)
  np.testing.assert_array_almost_equal(outputs, computed_outputs)


def test_block_with_laurel():
  num_heads = 2
  embed_dim = 4
  head_dim = 6
  cache_size = 3
  batch_size = 5
  seq_len = 1
  rank = 4

  inputs = jnp.ones((batch_size, seq_len, embed_dim))
  positions = jnp.zeros((batch_size, seq_len))

  # Initialize cache.
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )

  # Check that initial cache shape is correct.
  expected_cache_shape = (batch_size, cache_size, num_heads, head_dim)
  np.testing.assert_array_equal(cache['k'].shape, expected_cache_shape)
  np.testing.assert_array_equal(cache['v'].shape, expected_cache_shape)

  # Initialize and apply the block.
  block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=1,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_NANO_ATTN_TYPE,
      query_pre_attn_scalar=head_dim**-0.5,
      transpose_gating_einsum=False,
      use_laurel=True,
      laurel_rank=rank,
  )

  attn_mask = jnp.ones((batch_size, seq_len, cache_size))
  params = block.init(
      jax.random.PRNGKey(0), inputs, positions, cache, attn_mask
  )

  new_cache, outputs = block.apply(
      params, inputs, positions, cache, attn_mask
  )

  # Check that updated cache shape is correct.
  np.testing.assert_array_equal(new_cache['k'].shape, expected_cache_shape)
  np.testing.assert_array_equal(new_cache['v'].shape, expected_cache_shape)
  np.testing.assert_array_equal(new_cache['end_index'].shape, (batch_size,))

  # Check that output shape is correct.
  expected_output_shape = (batch_size, seq_len, embed_dim)
  np.testing.assert_array_equal(outputs.shape, expected_output_shape)


def test_per_layer_mapping():
  features = 4
  per_layer_dim = 3
  batch_size = 5
  seq_len = 1

  pli = jnp.ones((batch_size, seq_len, per_layer_dim))
  x = jnp.ones((batch_size, seq_len, features))
  per_layer_mapping = _modules.PerLayerMapping(
      embed_dim=features,
      per_layer_input_dim=per_layer_dim
  )

  params = per_layer_mapping.init(jax.random.PRNGKey(0), x, pli)
  output = per_layer_mapping.apply(params, x, pli)
  expected_shape = (batch_size, seq_len, features)
  np.testing.assert_array_equal(output.shape, expected_shape)


def test_block_with_per_layer_mapping():
  num_heads = 2
  embed_dim = 4
  head_dim = 6
  cache_size = 3
  batch_size = 5
  seq_len = 1
  per_layer_dim = 3

  inputs = jnp.ones((batch_size, seq_len, embed_dim))
  positions = jnp.zeros((batch_size, seq_len))
  pli = jnp.ones((batch_size, seq_len, per_layer_dim))

  # Initialize cache.
  cache = _modules.Attention.init_cache(
      cache_size=cache_size,
      num_heads=num_heads,
      head_dim=head_dim,
      batch_size=batch_size,
      dtype=jnp.float32,
  )

  # Check that initial cache shape is correct.
  expected_cache_shape = (batch_size, cache_size, num_heads, head_dim)
  assert cache['k'].shape == expected_cache_shape
  assert cache['v'].shape == expected_cache_shape

  # Initialize and apply the block.
  block = _modules.Block(
      num_heads=num_heads,
      num_kv_heads=num_heads,
      embed_dim=embed_dim,
      head_dim=head_dim,
      hidden_dim=1,
      use_post_attn_norm=False,
      use_post_ffw_norm=False,
      attn_type=_ATTN_TYPE,
      query_pre_attn_scalar=head_dim**-0.5,
      transpose_gating_einsum=False,
      per_layer_input_dim=per_layer_dim,
  )

  attn_mask = jnp.ones((batch_size, seq_len, cache_size))
  params = block.init(
      jax.random.PRNGKey(0), inputs, positions, cache, attn_mask,
      per_layer_input=pli
  )

  new_cache, outputs = block.apply(
      params, inputs, positions, cache, attn_mask, per_layer_input=pli
  )

  # Check that updated cache shape is correct.
  assert new_cache['k'].shape == expected_cache_shape
  assert new_cache['v'].shape == expected_cache_shape
  assert new_cache['end_index'].shape == (batch_size,)

  # Check that output shape is correct.
  expected_output_shape = (batch_size, seq_len, embed_dim)
  assert outputs.shape == expected_output_shape
