"""
    This file is part of BinCAT.
    Copyright 2014-2017 - Airbus Group

    BinCAT is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or (at your
    option) any later version.

    BinCAT is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with BinCAT.  If not, see <http://www.gnu.org/licenses/>.
"""
import logging
import idc
import idautils
import idaapi
from idabincat.analyzer_conf import ConfigHelpers

dump_log = logging.getLogger('bincat.plugin.dump_binary')
dump_log.setLevel(logging.DEBUG)


def dump_binary(fname):
    max_addr = 0
    # Check if we have a buggy IDA or not
    try:
        idaapi.get_many_bytes_ex(0, 1)
    except TypeError:
        buggy = True
    else:
        buggy = False
    if buggy:
        f = idaapi.qfile_t()
        f.open(fname, 'wb+')
        segments = [x for x in idautils.Segments()]
        max_addr = idc.GetSegmentAttr(segments[-1], idc.SEGATTR_END)
        # TODO check max_addr to see if it's sane to write such a big file
        idaapi.base2file(f.get_fp(), 0, 0, max_addr)
        f.close()

    else:
        with open(fname, 'wb+') as f:
            # over all segments
            for s in idautils.Segments():
                start = idc.GetSegmentAttr(s, idc.SEGATTR_START)
                end = idc.GetSegmentAttr(s, idc.SEGATTR_END)
                # print "Start: %x, end: %x, size: %x" % (start, end, end-start)
                max_addr = max(max_addr, end)
                f.seek(start, 0)
                # Only works with fixed IDAPython.
                f.write(idaapi.get_many_bytes_ex(start, end-start)[0])

    dump_log.debug("section[dump] = 0, 0x%x, 0, 0x%x", max_addr, max_addr)


if __name__ == '__main__':
    fname = ConfigHelpers.askfile("*.*", "Save to binary")
    dump_binary(fname)
