"""Rainfall inputs: stations with id, longitude, latitude and hourly[{time,precipitation_mm}].

Both history and forecast require timezone-aware ISO times and metadata source_url/issued_at.
Forecast has horizon >=3 hours. Historical data must precede forecast issuance.
"""
