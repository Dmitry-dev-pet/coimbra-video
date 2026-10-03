# Coimbra OpenTTD 002 — road network

002 converts the OSM transport reference from milestone 001 into a deterministic
512×512 OpenTTD tile plan.

The converter keeps only drivable road classes for this first pass, snaps the
geometry to a four-connected OpenTTD grid, and treats OSM bridge/tunnel/layer
semantics as grade-separated candidates. Grade-separated edges are **never**
silently converted to surface roads.

The build also emits an installable GameScript directory, `game/CoimbraBuilder`.
When selected for the matching 512×512 Coimbra heightmap, it attempts bridges and
tunnels first and then creates the surface road network as deity/town-owned roads.

This is still a review milestone: OpenTTD terrain rules can reject some real-world
bridge heads and tunnel portals after height quantization. Those failures are
logged and left absent rather than creating false intersections.
