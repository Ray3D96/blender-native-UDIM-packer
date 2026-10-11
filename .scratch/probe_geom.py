import mathutils, mathutils.geometry as g
print([n for n in dir(g) if 'intersect' in n.lower() or 'poly' in n.lower()])
