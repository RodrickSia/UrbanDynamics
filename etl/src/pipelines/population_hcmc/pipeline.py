from src.pipelines.population_hcmc import extract, load, transform


def run() -> None:
    """Run the population pipeline once extraction and loading are implemented."""
    raw_data = extract.run()
    normalized_data = transform.run(raw_data)
    load.run(normalized_data)
