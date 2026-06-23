"""World 1 tolerances, centralized.

All absolute (pixel) for now, validated on one 1325x2275 sample. The endgame
is many diagrams at different scales, where fixed pixels will not transfer.
When a second, differently-scaled sample forces the switch, replace these with
multiples of a characteristic length (stroke-width or median node size). That
becomes a single edit here, not a hunt across modules.

Do not scatter raw numbers in the stages. Import from here.
"""

# Classification
ARROWHEAD_MAX_SIDE = 80.0    # an arrowhead bbox side is small vs a node

# Assembly
ATTACH_TOL = 30.0            # arrowhead centroid to connector endpoint gap

# Endpoint matching
MATCH_TOL = 60.0             # connector end to nearest shape, max distance

# Text association
TEXT_PAD = 10.0              # slack when testing a text anchor inside a shape

