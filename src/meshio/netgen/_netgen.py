"""
I/O for Netgen mesh files.
"""
import numpy as np
import warnings

from ..__about__ import __version__
from .._common import _topological_dimension
from .._files import open_file
from .._helpers import register
from .._mesh import Mesh


def _fast_forward_over_blank_lines(f):
    is_eof = False
    while True:
        line = f.readline()
        if not line:
            is_eof = True
            break

        line = line.strip()
        if len(line) > 0 and not line.startswith("#"):
            break
    return line, is_eof


netgen0d_to_meshio_type = {
    1: "vertex",
}
netgen1d_to_meshio_type = {
    2: "line",
}
netgen2d_to_meshio_type = {
    3: "triangle",
    6: "triangle6",
    4: "quad",
    8: "quad8",
}

netgen3d_to_meshio_type = {
    4: "tetra",
    5: "pyramid",
    6: "wedge",
    8: "hexahedron",
    10: "tetra10",
    13: "pyramid13",
    15: "wedge15",
    20: "hexahedron20",
}

netgen_to_meshio_type = {
    0: netgen0d_to_meshio_type,
    1: netgen1d_to_meshio_type,
    2: netgen2d_to_meshio_type,
    3: netgen3d_to_meshio_type,
}

netgen_to_meshio_pmap = {
    "vertex": [0],
    "line": [0, 1],
    "triangle": list(range(3)),
    "triangle6": [0, 1, 2, 5, 3, 4],
    "quad": list(range(4)),
    "quad8": [0, 1, 2, 3, 4, 7, 5, 6],
    "tetra": [0, 2, 1, 3],
    "tetra10": [0, 2, 1, 3, 5, 7, 4, 6, 9, 8],
    "pyramid": [0, 3, 2, 1, 4],
    "pyramid13": [0, 3, 2, 1, 4, 7, 6, 8, 5, 9, 12, 11, 10],
    "wedge": [0, 2, 1, 3, 5, 4],
    "wedge15": [0, 2, 1, 3, 5, 4, 7, 8, 6, 13, 14, 12, 9, 11, 10],
    "hexahedron": [0, 3, 2, 1, 4, 7, 6, 5],
    "hexahedron20": [
        0,
        3,
        2,
        1,
        4,
        7,
        6,
        5,
        10,
        9,
        11,
        8,
        16,
        19,
        18,
        17,
        14,
        13,
        15,
        12,
    ],
}

meshio_to_netgen_pmap = {}
for t, pmap in netgen_to_meshio_pmap.items():
    n = len(pmap)
    ipmap = list(range(n))
    for i in range(n):
        ipmap[pmap[i]] = i
    meshio_to_netgen_pmap[t] = ipmap


def read(filename):
    if str(filename).endswith(".vol.gz"):
        import gzip

        with gzip.open(filename, "rt") as f:
            return read_buffer(f)

    with open_file(filename, "r") as f:
        return read_buffer(f)


def _read_cells(f, netgen_cell_type, cells, cells_index, skip_every_other_line=False):
    if netgen_cell_type == "pointelements":
        dim = 0
        nump = 1
        pi0 = 0
        i_index = 1
    elif netgen_cell_type.startswith("edgesegments"):
        dim = 1
        nump = 2
        pi0 = 2
        i_index = 0
    elif netgen_cell_type.startswith("surfaceelements"):
        dim = 2
        pi0 = 5
        i_index = 1
    elif netgen_cell_type == "volumeelements":
        dim = 3
        pi0 = 2
        i_index = 0
    else:
        raise ValueError("Unknown Netgen cell section: {}".format(netgen_cell_type))

    num_cells = int(f.readline())
    tmap = netgen_to_meshio_type[dim]

    for _ in range(num_cells):
        line, is_eof = _fast_forward_over_blank_lines(f)
        data = list(filter(None, line.split(" ")))
        index = int(data[i_index])
        if dim == 2:
            nump = int(data[4])
        elif dim == 3:
            nump = int(data[1])

        pi = list(map(int, data[pi0 : pi0 + nump]))

        t = tmap[nump]
        if len(cells) == 0 or t != cells[-1][0]:
            cells.append((t, []))
            cells_index.append([])
        cells[-1][1].append(pi)
        cells_index[-1].append(index)
        if skip_every_other_line:
            line, is_eof = _fast_forward_over_blank_lines(f)


def _write_cells(f, block, index=None):
    if len(block) == 0:
        return
    pmap = np.array(meshio_to_netgen_pmap[block.type])
    dim = _topological_dimension[block.type]
    post_data = []
    pre_data = []
    i_index = 0
    if dim == 0:
        post_data = [1]
        i_index = 1
    elif dim == 1:
        pre_data = [1, 0]
        post_data = [-1, -1, 0, 0, 1, 0, 1, 0]
    elif dim == 2:
        pre_data = [1, 1, 0, 0, len(pmap)]
        i_index = 1
    elif dim == 3:
        pre_data = [1, len(pmap)]
    else:
        raise ValueError(f"Invalid cell dimension: {dim}")

    col1 = len(pre_data)
    col2 = col1 + len(pmap)
    col3 = col2 + len(post_data)

    pi = np.zeros((len(block), col3), dtype=np.int32)
    pi[:, :col1] = np.repeat([pre_data], len(block), axis=0)
    pi[:, col1:col2] = block.data[:, pmap] + 1
    pi[:, col2:] = np.repeat([post_data], len(block), axis=0)
    if index is not None:
        pi[:, i_index] = index
    np.savetxt(f, pi, "%i")


def _skip_block(f):
    n = int(f.readline())
    for _ in range(n):
        f.readline()


def read_buffer(f):
    points = []
    cells = []
    cells_index = []

    have_edgesegmentsgi2_in_two_lines = False

    line, is_eof = _fast_forward_over_blank_lines(f)
    if line != "mesh3d":
        raise RuntimeError("Not a valid Netgen mesh")

    while True:
        line, is_eof = _fast_forward_over_blank_lines(f)
        if is_eof:
            break

        elif line == "dimension":
            dimension = int(f.readline())
        elif line == "geomtype":
            geomtype = int(f.readline())
            if geomtype not in [0, 1, 10, 11, 12, 13]:
                warnings.warn(f"Unkown geomtype in Netgen mesh: {geomtype}")

        elif line == "points":
            num_points = int(f.readline())
            if num_points > 0:
                points = np.loadtxt(f, max_rows=num_points)
                if dimension == 2:
                    points = points[:, :2]

        elif line in [
            "pointelements",
            "edgesegments",
            "edgesegmentsgi",
            "edgesegmentsgi2",
            "surfaceelements",
            "surfaceelementsgi",
            "surfaceelementsuv",
            "volumeelements",
        ]:
            _read_cells(f, line, cells, cells_index, have_edgesegmentsgi2_in_two_lines)
        elif line == "endmesh":
            break

        elif line == "identificationtypes":
            _ = int(f.readline())  # num_identifiactions
            _ = f.readline()  # identifications in one line

        elif line.split() == ["surf1", "surf2", "p1", "p2"]:
            # if this line is present, the edgesegmentsgi2 info is split in two lines per data set
            have_edgesegmentsgi2_in_two_lines = True

        elif line in [
            "bcnames",
            "cd2names",
            "cd3names",
            "face_colours",
            "identifications",
            "materials",
            "singular_edge_left",
            "singular_edge_right",
            "singular_face_inside",
            "singular_face_outside",
            "singular_points",
        ]:
            _skip_block(f)
        else:
            raise RuntimeError(f"Unknown Netgen mesh token: {line}")

    # convert to numpy arrays
    # subtract one (netgen counts 1-based)
    # apply permutation of vertex numbers
    for k, (t, data) in enumerate(cells):
        pmap = netgen_to_meshio_pmap[t]
        d = np.array(data, dtype=np.uint32)
        d[:, :] = d[:, pmap] - 1
        cells[k] = (t, d)

    mesh = Mesh(points, cells, cell_data={"netgen:index": cells_index})
    return mesh


def write(filename, mesh, float_fmt=".16e"):
    if str(filename).endswith(".vol.gz"):
        import gzip

        with gzip.open(filename, "wt") as f:
            return write_buffer(f, mesh, float_fmt)

    with open_file(filename, "w") as f:
        return write_buffer(f, mesh, float_fmt)


def write_buffer(f, mesh, float_fmt):
    num_points, dimension = mesh.points.shape
    cells_per_dim = [0, 0, 0, 0]
    cells_index = (
        mesh.cell_data["netgen:index"]
        if "netgen:index" in mesh.cell_data
        else [None] * len(mesh.cells)
    )
    for block in mesh.cells:
        cells_per_dim[_topological_dimension[block.type]] += len(block)

    f.write(f"# Generated by meshio {__version__}\n")
    f.write("mesh3d\n\n")

    f.write("dimension\n")
    f.write(f"{dimension}\n\n")

    f.write("geomtype\n")
    f.write("0\n")

    f.write("\n# surfnr    bcnr   domin  domout      np      p1      p2      p3\n")
    f.write("surfaceelements\n")
    f.write(f"{cells_per_dim[2]}\n")
    for block, index in zip(mesh.cells, cells_index):
        if _topological_dimension[block.type] == 2:
            _write_cells(f, block, index)

    f.write("\n#  matnr      np      p1      p2      p3      p4\n")
    f.write("volumeelements\n")
    f.write(f"{cells_per_dim[3]}\n")
    for block, index in zip(mesh.cells, cells_index):
        if _topological_dimension[block.type] == 3:
            _write_cells(f, block, index)

    f.write(
        "\n# surfid  0   p1   p2   trignum1    trignum2   domin/surfnr1    domout/surfnr2   ednr1   dist1   ednr2   dist2\n",
    )
    f.write("edgesegmentsgi2\n")
    f.write(f"{cells_per_dim[1]}\n")
    for block, index in zip(mesh.cells, cells_index):
        if _topological_dimension[block.type] == 1:
            _write_cells(f, block, index)

    f.write("\n#          X             Y             Z\n")
    f.write("points\n")
    f.write(f"{len(mesh.points)}\n")

    points = mesh.points
    if dimension == 2:
        points = np.column_stack((points, np.zeros(points.shape[0], dtype=points.dtype)))
    np.savetxt(f, points, "%" + float_fmt)

    f.write("\n#          pnum             index\n")
    f.write("pointelements\n")
    f.write(f"{cells_per_dim[0]}\n")
    for block, index in zip(mesh.cells, cells_index):
        if _topological_dimension[block.type] == 0:
            _write_cells(f, block, index)

    f.write("\nendmesh\n")


register("netgen", [".vol", ".vol.gz"], read, {"netgen": write})
