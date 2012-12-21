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

# Future proof since future versions of creator have renamed this
try:
    DisplayImageFile
except NameError:
    DisplayImageFile = DisplayImage

# Only cache it if we don't have it already. This allows us to easily
# reload without recursing through previous versions of our own code
try:
    creator_c_style_dumper
except NameError:
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
            with SubItem(d, "File"):
                d.putAddress(value.address)
                fileDumper.putInfo(d, value)

class ArrayFormatter(object):
    def __init__(self, typename):
        self._typename = typename
        mod_type = typename.replace('::', '__')
        globals()['qform__%s' % mod_type] = self.formats
        self._list = list()
        self._names = list()

    def addFormat(self, formatter):
        self._list.append(formatter)
        self._names.append(formatter.__name__)
        return formatter

    def formats(self):
        return ','.join(self._names)

    def callFormat(self, fmt, *args, **kwargs):
        return self._list[fmt - 1](*args, **kwargs)

    @catch_errors("array")
    def putInfo(self, d, value):
        d.putType(self._typename)
        d.putNumChild(0)
        if d.currentItemFormat() is not None:
            d.putValue(self.make_creator_output(d, value))
        else:
            d.putValue('')

class DebugWriter(ArrayFormatter):
    def make_creator_output(self, d, value, *args, **kwargs):
        # Dump memory to file. Necessary because nowhere does python run in
        # the same process (and address space) as actual debugger process.
        tmpname = dump_temp_file(value)

        # Read into numpy array in this process
        arr = load_numpy_array(tmpname, value)
        if arr is None:
            return

        self.callFormat(d.currentItemFormat(), arr, tmpname, *args, **kwargs)
        return tmpname + '.npy'

fileDumper = DebugWriter('debug::FileDump')

@fileDumper.addFormat
def Numpy(arr, fname, *args, **kwargs):
    np.save(fname, arr)

# Class to make it more flexible to add plot types. Just need to add
# simple function that takes an array. Name of the function is added
# as an option for display in creator and will be called as appropriate
class DebugPlotter(ArrayFormatter):
    def make_creator_output(self, d, value, *args, **kwargs):
        # Dump memory to file. Necessary because nowhere does python run in
        # the same process (and address space) as actual debugger process.
        tmpname = dump_temp_file(value)

        # Read into numpy array in this process
        arr = load_numpy_array(tmpname, value)
        if arr is None:
            return

        if np.iscomplexobj(arr):
            arr = np.abs(arr)

        # Some size parameters for generated images
        dpi = 100
        size = 512
        inches = float(size) / dpi
        fig = plt.figure(figsize=(inches, inches), dpi=dpi)

        # Change plot function based on format
        self.callFormat(d.currentItemFormat(), arr, *args, **kwargs)

        # Always save to temp file. 'raw' makes it compatible for QImage creation.
        plt.savefig(tmpname, format='raw', dpi=dpi)

        d.putDisplay(DisplayImageFile, " %d %d 5 %s" % (size, size, tmpname))
        return ''

defaultPlotter = DebugPlotter('debug::ImagePlot')

@defaultPlotter.addFormat
def Image(arr, origin='lower', interp='None', **kwargs):
    plt.imshow(arr, origin=origin, interpolation=interp)
    plt.colorbar()

@defaultPlotter.addFormat
def PPI(arr, **kwargs):
    naz, nrng = arr.shape
    az = np.linspace(0, 2 * np.pi, naz + 1)
    rng = np.arange(nrng + 1)
    x = rng * np.sin(az)[:, None]
    y = rng * np.cos(az)[:, None]
    plt.pcolormesh(x, y, arr)
    plt.colorbar()
    plt.gca().set_aspect('equal', 'datalim')

@defaultPlotter.addFormat
def Plot(arr, **kwargs):
    plt.plot(arr)

@defaultPlotter.addFormat
def Pcolor(arr, **kwargs):
    plt.pcolormesh(arr)
    plt.colorbar()

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

    # Return None if we don't have a corresponding numpy type
    base_type = base_type_map.get(typ.code, None)
    if base_type is None:
        return None

    if str(typ.unqualified()).startswith('unsigned'):
        leader = 'u'
    else:
        leader = ''
    return np.dtype("%s%s%d" % (leader, base_type, typ.sizeof * 8))

def dump_temp_file(value):
    tmp = tempfile.mkstemp(prefix="gdbpy_")
    tmpname = tmp[1].replace("\\", "\\\\")
    p = value.address

    # Dump memory to file. Necessary because nowhere does python run in
    # the same process (and address space) as actual debugger process.
    gdb.execute("dump binary memory %s %s %s" %
        (tmpname, cleanAddress(p), cleanAddress(p + 1)))
    return tmpname

def load_numpy_array(tmpname, value):
    shape, dtype = numpy_info(value)

    # We must have failed to get a shape or type
    if shape is None or dtype is None:
        return None

    # Read into numpy array in this process
    return np.fromfile(tmpname, dtype=dtype).reshape(*shape)
