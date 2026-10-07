from . import config,grid,extract,load

def run(boundary=None,refresh_history=False,**kwargs):
    settings = config.settings(boundary)
    cells,metadata = grid.build(settings)
    forecast = extract.forecast(settings,cells,metadata)
    history = (extract.history(settings,cells,metadata) if refresh_history
               else extract.history_cached(settings,cells,metadata))
    return load.run(forecast,history)
