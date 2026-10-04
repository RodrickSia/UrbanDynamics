from src.shared.database import publish
def run(document):
    return publish("flood_history", document)
