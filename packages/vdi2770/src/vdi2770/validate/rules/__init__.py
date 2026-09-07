"""Rules. No module here may import a parser — `tests/test_layering.py` fails on
`zipfile` or an XML library. The readers' reserved file names are the one thing
rules may take from that layer. A rule that cannot reach the parser cannot
accidentally validate the serialisation instead of the model.
"""
