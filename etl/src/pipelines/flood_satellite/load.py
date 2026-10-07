from src.shared.database import publish


def run(document):
    return publish(document["metadata"]["layer"], document)
