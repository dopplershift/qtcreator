# Dumper for the ProFile class used by QtCreator. Useful when trying to
# debug Creator.

def qdump__ProString(d, value):
    if isNull(value["m_string"]):
        d.putValue("(null)")
        d.putNumChild(0)
        return
    s = value["m_string"]
    data, size, alloc = d.stringData(s)
    data += 2 * int(value["m_offset"])
    size = int(value["m_length"])
    s = d.readRawMemory(data, 2 * size)
    d.putValue(s, Hex4EncodedLittleEndian)
    d.putNumChild(5)
    if d.isExpanded():
        with Children(d):
            d.putFields(value)
