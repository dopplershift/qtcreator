# This contains code to utilize Numpy and Matplotlib to make plots of
# arrays that display as images in Creator's debugger.
import tempfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def catch_errors(name="Error"):
    def dec(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                import sys
                showException(name, *sys.exc_info())
                return
        return wrapper
    return dec


creator_c_style_dumper = qdump____c_style_array__
@catch_errors("array")
def qdump____c_style_array__(d, value):
    typ = value.type.unqualified()

    # Make sure the array points to something we can plot, otherwise we
    # should just skip the plot code altogether.
    if typ.target().code not in (ArrayCode, IntCode, FloatCode, ComplexCode):
        return creator_c_style_dumper(d, value)

    d.putType(str(typ))
    d.putValue('')
    d.putNumChild(2)
    if d.isExpanded():
        with Children(d):
            with SubItem(d, "Data"):
                creator_c_style_dumper(d, value)
            with SubItem(d, "Image"):
                d.putAddress(value.address)
                defaultPlotter.putInfo(d, value)

# Class to make it more flexible to add plot types. Just need to add
# simple function that takes an array. Name of the function is added
# as an option for display in creator and will be called as appropriate
class DebugPlotter(object):
    def __init__(self, typename):
        self._typename = typename
        mod_type = typename.replace('::', '__')
        globals()['qform__%s' % mod_type] = self.formats
        self._list = list()
        self._names = list()

    def addPlot(self, plotter):
        self._list.append(plotter)
        self._names.append(plotter.__name__)
        return plotter

    def formats(self):
        return ','.join(self._names)

    def makePlot(self, fmt, *args, **kwargs):
        return self._list[fmt - 1](*args, **kwargs)

    @catch_errors("array")
    def putInfo(self, d, value):
        d.putValue('')
        d.putType(self._typename)
        d.putNumChild(0)
        self.plot_memory(d, value)

    def plot_memory(self, d, value, shape=None, dtype=None, *args, **kwargs):
        if shape is None or dtype is None:
            find_shape, find_dtype = numpy_info(value)
            if shape is None:
                shape = find_shape
            if dtype is None:
                dtype = find_dtype

        format = d.currentItemFormat()
        tmp = tempfile.mkstemp(prefix="gdbpy_")
        tmpname = tmp[1].replace("\\", "\\\\")
        p = value.address

        # Dump memory to file. Necessary because nowhere does python run in
        # the same process (and address space) as actual debugger process.
        gdb.execute("dump binary memory %s %s %s" %
            (tmpname, cleanAddress(p), cleanAddress(p + 1)))

        # Read into numpy array in this process
        warn("Numpy Conversion--Shape: %s dtype: %s" % (shape, dtype))
        arr = np.fromfile(tmpname, dtype=dtype).reshape(*shape)

        # Some size parameters for generated images
        dpi = 100
        size = 512
        inches = float(size) / dpi
        fig = plt.figure(figsize=(inches, inches), dpi=dpi)

        # Change plot function based on format
        self.makePlot(format, arr, *args, **kwargs)

        # Always save to temp file. 'raw' makes it compatible for QImage creation.
        plt.savefig(tmpname, format='raw', dpi=dpi)

        d.putDisplay(DisplayImageFile, " %d %d 5 %s" % (size, size, tmpname))

defaultPlotter = DebugPlotter('debug::ImagePlot')

@defaultPlotter.addPlot
def Image(arr, origin='lower', interp='None', **kwargs):
    plt.imshow(arr, origin=origin, interpolation=interp)
    plt.colorbar()

@defaultPlotter.addPlot
def PPI(arr, **kwargs):
    naz, nrng = arr.shape
    az = np.linspace(0, 2 * np.pi, naz + 1)
    rng = np.arange(nrng + 1)
    x = rng * np.sin(az)[:, None]
    y = rng * np.cos(az)[:, None]
    plt.pcolormesh(x, y, arr)
    plt.colorbar()
    plt.gca().set_aspect('equal', 'datalim')

@defaultPlotter.addPlot
def Plot(arr, **kwargs):
    plt.plot(arr)

def numpy_info(value):
    '''Determine the type and shape of a numpy array to hold the C array
    represented by the GDB value passed in'''
    typ = value.type
    shape = list()
    while typ.code == ArrayCode:
        shape.append(typ.sizeof)
        if len(shape) > 1:
            shape[-2] /= shape[-1]
        value = value.dereference()
        typ = value.type
    shape[-1] /= value.type.sizeof
    return tuple(shape), dtypeof(typ)

def dtypeof(typ):
    '''Maps a GDB type to a Numpy dtype'''
    base_type_map = {gdb.TYPE_CODE_INT:"int", gdb.TYPE_CODE_FLT:"float",
            gdb.TYPE_CODE_COMPLEX:"complex"}
    base_type = base_type_map[typ.code]
    if str(typ.unqualified()).startswith('unsigned'):
        leader = 'u'
    else:
        leader = ''
    return np.dtype("%s%s%d" % (leader, base_type, typ.sizeof * 8))
