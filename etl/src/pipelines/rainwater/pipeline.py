from src.pipelines.rainwater import extract, load, transform


def run() -> None:
    """Run the rainwater pipeline once its source and transformations are defined."""
    raw_data = extract.run()
    normalized_data = transform.run(raw_data)
    load.run(normalized_data)
