"""Rules. Nothing here may import a reader or a parser — enforced by
tests/test_layering.py. A rule that cannot reach the parser cannot accidentally
validate the serialisation instead of the model.
"""
