import pytest
import os
from util import AARCH64

arm = AARCH64(
    os.path.join(os.path.dirname(os.path.realpath(__file__)),'armv8_isn.ini.in')
)
compare = arm.compare

mov_imm = pytest.mark.parametrize("op", ["movz", "movk", "movn"])
dataop_comp_logic = pytest.mark.parametrize("op", ["and", "eor", "orr", "bic"])
dataop_comp_arith = pytest.mark.parametrize("op", ["sub", "add"])

# XXX make this work ? PC is actually random because of ASLR
#def test_adrp(tmpdir, op32):
#    asm = """
#    label:
#        adrp x0, label
#    """.format(**locals())
#    compare(tmpdir, asm, ["x0"])

def test_data_xfer_offsets(tmpdir, armv8off):
    asm = """
            mov x0, #0
            mov x1, #123
            mov x2, #101
            stp x1, x2, [sp, #{armv8off}]
            ldp x3, x4, [sp, #{armv8off}]
    """.format(**locals())
    compare(tmpdir, asm, ["x0", "x1", "x2", "x3", "x4"])

@mov_imm
def test_mov(tmpdir, op, op16):
    asm = """
        mov x0, 0
        sub x0, x0, 1
        {op} x0, #{op16}
        mov w1, w0
        mov w2, w1
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1","x2"])

@dataop_comp_logic
def test_data_proc_logic_imm(tmpdir, op, armv7op, armv7op_, armv8bitmasks):
    asm = """
            mov x0, #{armv7op}
            mov x1, #{armv7op_}
            {op} x2, x0, #{armv8bitmasks}
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

@dataop_comp_logic
def test_data_proc_logic(tmpdir, op, armv7op, armv7op_):
    asm = """
            mov x0, #{armv7op}
            mov x1, #{armv7op_}
            {op} x2, x0, x1
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

@dataop_comp_arith
def test_data_proc_arith(tmpdir, op, armv7op, armv7op_):
    asm = """
            mov x0, #{armv7op}
            mov x1, #{armv7op_}
            {op} x2, x0, x1
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

@dataop_comp_logic
def test_data_proc_logic_32(tmpdir, op, armv7op, armv7op_):
    asm = """
            mov w0, #{armv7op}
            mov w1, #{armv7op_}
            {op} w2, w0, w1
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

@dataop_comp_arith
def test_data_proc_arith_32(tmpdir, op, armv7op, armv7op_):
    asm = """
            mov w0, #{armv7op}
            mov w1, #{armv7op_}
            {op} w2, w0, w1
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

def test_ubfm(tmpdir, op6, op6_, armv7op, armv7op_):
    asm = """
            mov x0, #{armv7op}
            mov x1, #{armv7op_}
            UBFM x2, x0, #{op6}, #{op6_}
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])

def test_ubfm32(tmpdir, op6_32, op6_32_, armv7op, armv7op_):
    asm = """
            mov w0, #{armv7op}
            mov w1, #{armv7op_}
            UBFM w2, w0, #{op6_32}, #{op6_32_}
    """.format(**locals())
    compare(tmpdir, asm, ["x0","x1", "x2"])
