# Existing buildings, school scenarios and demolition estimates

Quick estimates use the same demand coefficients before and after development.
When generated or mapped existing buildings are available, their footprint,
floor count and use supply the estimated baseline for residents, water,
wastewater, energy, peak power and travel demand, including whole-scenario runs.
These are estimates, not surveyed occupancy. If no building inventory exists,
baseline occupancy remains unknown rather than implying vacant land.

Existing buildings remain in the final design unless their parcel has a saved
demolition mask. Demolition-only parcels also participate in a whole-scenario
simulation. New buildings are added to retained buildings.
An editor building with exactly the same footprint replaces that baseline
representation as a remodel; the same building is never counted twice.

School is available as a building and floor use. Default demo assumptions are
10 m² of physical school floor area per student and 15 students per staff member,
rounded up. Students are daytime users, not residents. Both assumptions can be
edited in Simulation. They are not legal school design or capacity standards.

Where an existing inventory is available, the demo connection limits for water,
wastewater and peak power assume 125% of estimated existing demand (minimum
1 m³/day or 1 kW). These are explicitly synthetic, apply only to the connection
in this study, and exclude external loads. They do not establish actual spare
utility capacity or the feasibility of a connection.

Demolition costs first use existing floor area within the union of demolition
masks: clipped footprint × floors. Missing floors use height / 3.2 m, or two
floors when height is also missing. Masks without building records assume
60% building coverage × two floors. Overlapping masks are counted once.
If no demolition quote is supplied, the demo assumes 200,000 VND/m² of demolished
floor area. Source labels and warnings identify these assumptions. A user quote
and surveyed area override the respective defaults. Included demolition remains
zero additional cost. Construction totals include demolition once.

Saved runs retain their captured inputs. Run Quick estimate again after updating
the application to create a result with the new baseline method.
