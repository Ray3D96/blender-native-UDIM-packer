import mathutils.geometry as g
# try different input formats for tessellate_polygon
try:
    r = g.tessellate_polygon([0,0, 1,0, 1,1, 0,1])
    print("flat floats OK:", r)
except Exception as e:
    print("flat floats FAIL:", e)
try:
    r = g.tessellate_polygon([(0,0),(1,0),(1,1),(0,1)])
    print("2d tuples OK:", r)
except Exception as e:
    print("2d tuples FAIL:", e)
