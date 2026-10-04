from src.shared.database import publish
def run(document):
    return publish("land_price", document)
