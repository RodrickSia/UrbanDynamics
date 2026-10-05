from . import extract, load, transform


def run(source=None, boundary=None, **kwargs):
    path, provenance = extract.run(source)
    document = transform.run(path, boundary)
    document["metadata"]["provenance"] = provenance
    return load.run(document)
