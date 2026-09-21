"""Hypothesis strategies for hostile `meta` payloads, shared by the property tests."""

from __future__ import annotations

from hypothesis import strategies as st

# Deliberately adversarial: deeply nested containers, unusual scalar types,
# and non-JSON-serializable values (a raw object, bytes). Circular
# references are exercised separately below, since hypothesis strategies
# can't easily generate them.
scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(),
    st.binary(),
    st.builds(object),
)

meta_values = st.recursive(
    scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5),
    ),
    max_leaves=25,
)

meta_dicts = st.dictionaries(st.text(min_size=1, max_size=10), meta_values, max_size=8)

# Text that includes what `st.text()` normally leaves out (lone surrogates),
# for the formatters, which must cope with whatever string a caller passes.
hostile_text = st.text(alphabet=st.characters(blacklist_categories=()), max_size=40)
