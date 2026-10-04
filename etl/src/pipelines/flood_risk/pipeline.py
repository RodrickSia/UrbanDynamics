from . import extract, transform, load
def run(weather_input=None, history_input=None, **kwargs):
    return load.run(transform.run(*extract.run(weather_input, history_input)))
