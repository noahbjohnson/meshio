# -*- coding: utf-8 -*-
#
__version__ = '0.1.4'
__author__ = 'Nico Schlömer'
__author_email__ = 'nico.schloemer@gmail.com'
__website__ = 'https://github.com/nschloe/meshio'

from . import h5m_io
from . import msh_io
from . import vtk_io


def read(filename, timestep=None):
    '''Reads an unstructured mesh with added data.

    :param filenames: The files to read from.
    :type filenames: str
    :param timestep: Time step to read from, in case of an Exodus input mesh.
    :type timestep: int, optional
    :returns mesh{2,3}d: The mesh data.
    :returns point_data: Point data read from file.
    :type point_data: dict
    :returns field_data: Field data read from file.
    :type field_data: dict
    '''
    import os

    # http://stackoverflow.com/questions/4843173/how-to-check-if-a-type-of-variable-is-string-in-python
    assert isinstance(filename, str)

    # serial files
    extension = os.path.splitext(filename)[1]

    # setup the reader
    if extension == '.msh':
        points, cells_nodes = msh_io.read(filename)
        return points, cells_nodes, None, None, None
    # setup the reader
    elif extension == '.h5m':
        return h5m_io.read(filename)
    elif extension == '.vtu':
        return vtk_io.read('vtu', filename)
    elif extension == '.vtk':
        return vtk_io.read('vtk', filename)
    elif extension in ['.ex2', '.exo', '.e']:
        return vtk_io.read('exodus', filename)
    else:
        raise RuntimeError('Unknown file type \'%s\'.' % filename)


def write(filename,
          points,
          cells,
          point_data=None,
          cell_data=None,
          field_data=None
          ):
    '''Writes mesh together with data to a file.

    :params filename: File to write to.
    :type filename: str

    :params point_data: Named additional point data to write to the file.
    :type point_data: dict
    '''
    import os

    extension = os.path.splitext(filename)[1]

    if extension == '.h5m':
        h5m_io.write(
            filename, points, cells,
            point_data=point_data,
            cell_data=cell_data,
            field_data=field_data
            )
    elif extension == '.msh':
        msh_io.write(filename, points, cells)
    elif extension == '.vtu':  # vtk xml format
        vtk_io.write(
            'vtu', filename, points, cells,
            point_data=point_data,
            cell_data=cell_data,
            field_data=field_data
            )
    elif extension == '.pvtu':  # parallel vtk xml format
        vtk_io.write(
            'pvtu', filename, points, cells,
            point_data=point_data,
            cell_data=cell_data,
            field_data=field_data
            )
    elif extension == '.vtk':  # classical vtk format
        vtk_io.write(
            'vtk', filename, points, cells,
            point_data=point_data,
            cell_data=cell_data,
            field_data=field_data
            )
    elif extension in ['.ex2', '.exo', '.e']:  # exodus ii format
        vtk_io.write(
            'exodus', filename, points, cells,
            point_data=point_data,
            cell_data=cell_data,
            field_data=field_data
            )
    else:
        raise RuntimeError('unknown file type \'%s\'.' % filename)
    return
