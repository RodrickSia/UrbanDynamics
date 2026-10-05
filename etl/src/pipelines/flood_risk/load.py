from src.shared.database import publish


def run(document):
    return publish("flood_risk", document)
