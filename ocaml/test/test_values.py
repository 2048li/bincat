import pytest
import subprocess
import copy
import binascii
import os.path
import itertools
from collections import defaultdict
from pybincat import cfa

def counter(fmt="%i", i=0):
    while True:
        yield fmt % i
        i += 1

GCC_DIR = counter("gcc-%i")
NASM_DIR = counter("nasm-%i")

ALL_FLAGS = ["cf","pf", "af", "zf","sf","df","of"]
ALL_REGS = ["eax","ebx","ecx","edx", "esi","edi","esp", "ebp"] + ALL_FLAGS

SOME_SHIFT_COUNTS = [0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 24, 31, 32, 33, 48, 63, 64, 65, 127, 128, 129 ]

SOME_OPERANDS_8 = [ 0, 1, 2, 7, 8, 0xf, 0x7f, 0x80, 0x81, 0xff]
SOME_OPERANDS_16 = SOME_OPERANDS_8 + [0x1234, 0x7fff, 0x8000, 0x8001, 0xfa72, 0xffff]
SOME_OPERANDS = SOME_OPERANDS_16 + [0x12345678, 0x1812fada, 0x12a4b4cd, 0x7fffffff, 0x80000000, 0x80000001, 0xffffffff ]
SOME_OPERANDS_64 = SOME_OPERANDS + [ 0x123456789, 0x100000000000,  0x65a227c6f24c562a,
                                     0x7fffffffffffffff, 0x8000000000000000, 0x80000000000000001,
                                     0xa812f8c42dec45ab, 0xffff123456789abc,  0xffffffffffffffff ]

SOME_OPERANDS_COUPLES_8 = list(itertools.product(SOME_OPERANDS_8, SOME_OPERANDS_8))
SOME_OPERANDS_COUPLES_16 = list(itertools.product(SOME_OPERANDS_16, SOME_OPERANDS_16))
SOME_OPERANDS_COUPLES = list(itertools.product(SOME_OPERANDS, SOME_OPERANDS))


def assemble(tmpdir, asm):
    d = tmpdir.mkdir(NASM_DIR.next())
    inf = d.join("asm.S")
    outf = d.join("opcodes")
    inf.write("BITS 32\n"+asm)
    listing = subprocess.check_output(["nasm", "-l", "/dev/stdout", "-o", str(outf), str(inf)])
    opcodes = open(str(outf)).read()
    return str(outf),listing,opcodes


def cpu_run(tmpdir, opcodesfname):
    out = subprocess.check_output(["./eggloader_x86",opcodesfname])
    regs = { reg: int(val,16) for reg, val in
            (l.strip().split("=") for l in out.splitlines()) }
    flags = regs.pop("eflags")
    regs["cf"] = flags & 1
    regs["pf"] = (flags >> 2) & 1
    regs["af"] = (flags >> 4) & 1
    regs["zf"] = (flags >> 6) & 1
    regs["sf"] = (flags >> 7) & 1
    regs["df"] = (flags >> 10) & 1
    regs["of"] = (flags >> 11) & 1
    return regs


def getReg(my_state, name):
    v = cfa.Value('reg', name, cfa.reg_len(name))
    return my_state[v][0]
def getLastState(prgm):
    curState = prgm['0']
    while True:
        nextStates = prgm.next_states(curState.node_id)
        if len(nextStates) == 0:
            return curState
        assert len(nextStates) == 1, \
            "expected exactly 1 destination state after running this instruction"
        curState = nextStates[0]

def prettify_listing(asm):
    s = []
    for l in asm.splitlines():
        l = l.strip()
        if "BITS 32" in l or len(l.split()) <= 1:
            continue
        if l:
            s.append("\t"+l)
    return "\n".join(s)


def extract_directives_from_asm(asm):
    d = defaultdict(dict)
    for l in asm.splitlines():
        if "@override" in l:
            sl = l.split()
            addr = int(sl[1],16)
            val = sl[sl.index("@override")+1]
            d["override"][addr] = val 
    return d


def bincat_run(tmpdir, asm):
    opcodesfname,listing,opcodes = assemble(tmpdir, asm)

    directives = extract_directives_from_asm(listing)
    
    outf = tmpdir.join('end.ini')
    logf = tmpdir.join('log.txt')
    initf = tmpdir.join('init.ini')
    initf.write(
        open("test_values.ini").read().format(
            code_length = len(opcodes),
            filepath = opcodesfname,
            overrides = "\n".join("%#010x=%s" % (addr, val) for addr,val in directives["override"].iteritems())
        )
    )

    try:
        prgm = cfa.CFA.from_filenames(str(initf), str(outf), str(logf))
    except Exception,e:
        return e, listing, opcodesfname

    last_state = getLastState(prgm)
    
    return { reg : getReg(last_state, reg) for reg in ALL_REGS}, listing, opcodesfname


def compare(tmpdir, asm, regs=ALL_REGS, reg_taints={}, top_allowed={}):
    bincat,listing, opcodesfname = bincat_run(tmpdir, asm)
    try:
        cpu = cpu_run(tmpdir, opcodesfname)
    except subprocess.CalledProcessError,e:
        pytest.fail("%s\n%s"%(e,asm))
    assert  not isinstance(bincat, Exception), repr(bincat)+"\n"+prettify_listing(listing)+"\n=========================\n"+"\n".join("cpu : %s = %08x" % (r,cpu[r]) for r in regs)
    
    diff = []
    same = []
    for r in regs:
        vtop = bincat[r].vtop
        value = bincat[r].value
        if cpu[r] & ~vtop != value & ~vtop:
            diff.append("- cpu   :  %s = %08x" % (r, cpu[r]))
            diff.append("+ bincat:  %s = %08x  %r" % (r,value,bincat[r]))
        else:
            same.append("  both  :  %s = %08x  %r" % (r, value,bincat[r]))
        allow_top = top_allowed.get(r,0)
        if vtop & ~allow_top:
            diff.append("+ top allowed:  %s = %08x ? %08x" % (r,cpu[r], allow_top))
            diff.append("+ bincat     :  %s = %08x ? %08x  %r" % (r,value,vtop,bincat[r]))
    assert not diff, "\n"+prettify_listing(listing)+"\n=========================\n"+"\n".join(diff)+"\n=========================\n"+"\n".join(same)
    diff = []
    for r,t in reg_taints.iteritems():
        if bincat[r].taint != t:
            diff.append("- expected :  %s = %08x ! %08x" % (r, cpu[r], t))
            diff.append("+ bincat   :  %s = %08x ! %08x  %r" % (r, bincat[r].value, bincat[r].taint, bincat[r]))
        else:
            same.append("  both     :  %s = %08x ! %08x  %r" % (r, bincat[r].value, bincat[r].taint, bincat[r]))
    assert not diff, "\n"+prettify_listing(listing)+"\n=========================\n"+"\n".join(diff)+"\n=========================\n"+"\n".join(same)
    

def test_assign(tmpdir):
    asm = """
    	mov eax,0xaaaa55aa
	mov ebx,0xcccccc55
    """
    compare(tmpdir, asm, ["eax","ebx"])

##  ___  ___  _        __  ___  ___  ___ 
## | _ \/ _ \| |      / / | _ \/ _ \| _ \
## |   / (_) | |__   / /  |   / (_) |   /
## |_|_\\___/|____| /_/   |_|_\\___/|_|_\
##                                       

def test_rotate_rol_reg32(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rol eax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_ror_reg32(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            ror eax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rol_reg16(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rol ax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_ror_reg16(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            ror ax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rol_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            rol eax,%i
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_ror_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            ror eax,%i
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})


##  ___  ___ _        __  ___  ___ ___ 
## | _ \/ __| |      / / | _ \/ __| _ \
## |   / (__| |__   / /  |   / (__|   /
## |_|_\\___|____| /_/   |_|_\\___|_|_\
##                                     

def test_rotate_rcl_reg32(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rcl eax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop,i,j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rcr_reg32(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rcr eax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop,i,j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rcl_reg16(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rcl ax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop,i,j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rcr_reg16(tmpdir):
    asm = """
            %s
            mov cl,%i
            mov eax, %#x
            rcr ax,cl
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop,i,j), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rcl_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            rcl eax,%i
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})

def test_rotate_rcr_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            rcr eax,%i
    """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "cf", "of"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0})


##  ___ _  _ _        __  ___ _  _ ___     __  ___   _   _        __
## / __| || | |      / / / __| || | _ \   / / / __| /_\ | |      / /
## \__ \ __ | |__   / /  \__ \ __ |   /  / /  \__ \/ _ \| |__   / / 
## |___/_||_|____| /_/   |___/_||_|_|_\ /_/   |___/_/ \_\____| /_/  
##                                                                  
##  ___   _   ___     __  ___ _  _ _    ___      __  ___ _  _ ___ ___  
## / __| /_\ | _ \   / / / __| || | |  |   \    / / / __| || | _ \   \ 
## \__ \/ _ \|   /  / /  \__ \ __ | |__| |) |  / /  \__ \ __ |   / |) |
## |___/_/ \_\_|_\ /_/   |___/_||_|____|___/  /_/   |___/_||_|_|_\___/ 
##                                                                     

def test_shift_shl_reg32(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            shl eax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_shl_reg16(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            shl ax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 16 else 0})

def test_shift_shl_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            shl eax, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_shr_reg32(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            shr eax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_shr_reg16(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            shr ax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 16 else 0})

def test_shift_shr_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            shr eax, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_sal_reg32(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            sal eax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})


def test_shift_sal_reg16(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            sal ax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 16 else 0})


def test_shift_sal_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            sal eax, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_sar_reg32(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            sar eax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_sar_reg16(tmpdir):
    asm = """
            %s
            mov cl, %i
            mov eax, %#x
            sar ax, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 16 else 0})

def test_shift_sar_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            sar eax, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if i >= 32 else 0})

def test_shift_shld_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            shld eax, ebx, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffffffff if (i>32) else 0})

def test_shift_shld_reg32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            mov cl, %i
            shld eax, ebx, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffffffff if (i>32) else 0})

def test_shift_shld_on_mem32(tmpdir):
    asm = """
            %s
            push 0x12b4e78f
            push 0
            mov ebx, %i
            mov cl, %i
            shld [esp+4], ebx, cl
            pop eax
            pop eax
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffffffff if (i>32) else 0})

def test_shift_shld_on_mem16(tmpdir):
    asm = """
            %s
            push 0x12b4e78f
            push 0
            mov ebx, %i
            mov cl, %i
            shld [esp+4], bx, cl
            pop eax
            pop eax
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if (i>16) else 0,
                                       "eax":0xffff if (i>32) else 0})

def test_shift_shld_reg16(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            mov cl, %i
            shld ax, bx, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "cf": 1 if (i>16) else 0,
                                       "eax":0xffff if (i>16) else 0})

def test_shift_shrd_imm8(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            shrd eax, ebx, %i
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, j, i), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffffffff if (i>32) else 0})

def test_shift_shrd_reg32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            mov cl, %i
            shrd eax, ebx, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffffffff if (i>32) else 0})

def test_shift_shrd_reg16(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, 0xa5486204
            mov cl, %i
            shrd ax, bx, cl
          """
    for i in SOME_SHIFT_COUNTS:
        for j in SOME_OPERANDS:
            for carryop in ["stc", "clc"]:
                compare(tmpdir, asm % (carryop, i, j), ["eax", "ebx", "of", "cf"],
                        top_allowed = {"of": 1 if (i&0x1f) != 1 else 0,
                                       "eax":0xffff if (i>16) else 0})

##    _   ___ ___ _____ _  _ __  __ ___ _____ ___ ___    ___  ___  ___ 
##   /_\ | _ \_ _|_   _| || |  \/  | __|_   _|_ _/ __|  / _ \| _ \/ __|
##  / _ \|   /| |  | | | __ | |\/| | _|  | |  | | (__  | (_) |  _/\__ \
## /_/ \_\_|_\___| |_| |_||_|_|  |_|___| |_| |___\___|  \___/|_|  |___/
##                                                                     

def test_add_imm32(tmpdir):
    asm = """
            mov eax, %#x
            add eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_add_reg32(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            add eax, ebx
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_add_reg16(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            add ax, bx
          """
    for vals in SOME_OPERANDS_COUPLES_16:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sub_imm32(tmpdir):
    asm = """
            mov eax, %#x
            sub eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sub_reg32(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            sub eax, ebx
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sub_reg16(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            sub ax, bx
          """
    for vals in SOME_OPERANDS_COUPLES_16:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])


def test_carrytop_adc(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            adc eax, ebx
          """
    for (a,b) in SOME_OPERANDS_COUPLES:
        topmask = (a+b)^(a+b+1)
        compare(tmpdir, asm % (a, b),
                ["eax", "of", "sf", "zf", "cf", "pf", "af"],
                top_allowed = {"eax":topmask,
                               "zf":1,
                               "pf": 1 if topmask & 0xff != 0 else 0,
                               "af": 1 if topmask & 0xf != 0 else 0,
                               "cf": 1 if topmask & 0x80000000 != 0 else 0,
                               "of": 1 if topmask & 0x80000000 != 0 else 0,
                               "sf": 1 if topmask & 0x80000000 != 0 else 0 })

def test_adc_reg32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, %#x
            adc eax, ebx
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES:
            compare(tmpdir, asm % (carryop,val1,val2), ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_adc_reg16(tmpdir):
    asm = """
            %s
            mov edx, %#x
            mov ecx, %#x
            adc dx, cx
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES_16:
            compare(tmpdir, asm % (carryop, val1, val2), ["edx", "of", "sf", "zf", "cf", "pf", "af"])

def test_adc_imm32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            adc eax, %#x
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES:
            compare(tmpdir, asm % (carryop, val1, val2), ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sbb_reg32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, %#x
            sbb eax, ebx
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES:
            compare(tmpdir, asm % (carryop,val1,val2), ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sbb_reg16(tmpdir):
    asm = """
            %s
            mov eax, %#x
            mov ebx, %#x
            sbb ax, bx
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES_16:
            compare(tmpdir, asm % (carryop, val1, val2), ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_sbb_imm32(tmpdir):
    asm = """
            %s
            mov eax, %#x
            sbb eax, %#x
          """
    for carryop in ["stc","clc"]:
        for val1,val2 in SOME_OPERANDS_COUPLES:
            compare(tmpdir, asm % (carryop, val1, val2), ["eax", "of", "sf", "zf", "cf", "pf", "af"])


def test_cmp_reg32(tmpdir):
    asm = """
            mov eax, %#x
            cmp eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_cmovxx_reg32(tmpdir):
    asm = """
            pushf
            pop eax
            and eax, 0xfffff72a
            or eax, %#x
            push eax
            popf
            mov edx, 0xdeadbeef
            xor ebx,ebx
            cmov%s ebx, edx
            xor ecx,ecx
            cmov%s ecx, edx
          """
    for f in range(0x40): # all flags combinations
        flags = (f&0x20<<6) | (f&0x10<<3) | (f&8<<3) | (f&4<<2) | (f&2<<1) | (f&1)
        for cond1, cond2 in [("a","be"),("ae","b"),("c","nc"), ("e", "ne"),
                             ("g","le"), ("ge","l"), ("o", "no"), ("s", "ns"),
                             ("p", "np") ]:
            compare(tmpdir, asm % (flags, cond1, cond2),
                    ["ebx", "ecx", "edx", "of", "sf", "zf", "cf", "pf", "af"],
                    top_allowed={ "af":1 })

def test_inc_reg32(tmpdir):
    asm = """
            mov eax, %#x
            inc eax
          """
    for vals in SOME_OPERANDS:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "pf", "af"])

def test_dec_reg32(tmpdir):
    asm = """
            mov eax, %#x
            dec eax
          """
    for vals in SOME_OPERANDS:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "pf", "af"])

def test_and_reg32(tmpdir):
    asm = """
            mov eax, %#x
            and eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf"])

def test_or_reg32(tmpdir):
    asm = """
            mov eax, %#x
            or eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf"])

def test_xor_reg32(tmpdir):
    asm = """
            mov eax, %#x
            xor eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf"])

def test_not_reg32(tmpdir):
    asm = """
            mov eax, %#x
            not eax
          """
    for vals in SOME_OPERANDS:
        compare(tmpdir, asm % vals, ["eax"])

def test_neg_reg32(tmpdir):
    asm = """
            mov eax, %#x
            neg eax
          """
    for vals in SOME_OPERANDS:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_neg_reg16(tmpdir):
    asm = """
            mov eax, %#x
            neg ax
          """
    for vals in SOME_OPERANDS:
        compare(tmpdir, asm % vals, ["eax", "of", "sf", "zf", "cf", "pf", "af"])

def test_test_reg32(tmpdir):
    asm = """
            mov eax, %#x
            test eax, %#x
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "sf", "zf", "pf"])

def test_idiv_reg32(tmpdir):
    asm = """
            mov edx, %#x
            mov eax, %#x
            mov ebx, %#x
            idiv ebx
          """
    for p in SOME_OPERANDS_64:
        for q in SOME_OPERANDS:
            if q != 0:
                ps = p if (p >> 63) == 0 else p|((-1)<<64)
                qs = q if (q >> 31) == 0 else q|((-1)<<32)
                if -2**31 <= ps/qs < 2**31:
                    compare(tmpdir, asm % (p>>32,p&0xffffffff,q), ["eax", "ebx", "edx"])

def test_idiv_reg8(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            idiv bl
          """
    for p in SOME_OPERANDS_16:
        for q in SOME_OPERANDS_8:
            if q != 0:
                ps = p if (p >> 15) == 0 else p|((-1)<<15)
                qs = q if (q >> 7) == 0 else q|((-1)<<7)
                if -2**7 <= ps/qs < 2**7:
                    compare(tmpdir, asm % (p,q), ["eax", "ebx"])

def test_div_reg32(tmpdir):
    asm = """
            mov edx, %#x
            mov eax, %#x
            mov ebx, %#x
            div ebx
          """
    for p in SOME_OPERANDS_64:
        for q in SOME_OPERANDS:
            if q != 0:
                if p/q < 2**32:
                    compare(tmpdir, asm % (p>>32,p&0xffffffff,q), ["eax", "ebx", "edx"])

def test_div_reg8(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            div bl
          """
    for p in SOME_OPERANDS_16:
        for q in SOME_OPERANDS_8:
            if q != 0:
                if p/q < 2**8:
                    compare(tmpdir, asm % (p,q), ["eax", "ebx"])



def test_mul_reg32(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            mul ebx
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "edx", "of", "cf"])

def test_mul_taint(tmpdir):
    asm = """
            mov eax, %#x  ; @override reg[eax],%#x 
            mov ebx, %#x  ; @override reg[ebx],%#x
            mul ebx
          """

    compare(tmpdir, asm % (1,0xff, 0x10001, 0),["eax", "ebx","edx"],
            reg_taints = dict(eax=0xff00ff, edx=0))
    
def test_imul3_reg32_imm(tmpdir):
    asm = """
            mov ecx, %#x
            mov ebx, %#x
            imul ecx, ebx, %#x
          """
    for val1, val2 in SOME_OPERANDS_COUPLES:
        for imm in SOME_OPERANDS:
            compare(tmpdir, asm % (val1, val2, imm), ["ecx", "ebx", "of", "cf"])

def test_imul3_reg16_imm(tmpdir):
    asm = """
            mov ecx, %#x
            mov ebx, %#x
            imul cx, bx, %#x
          """
    for val1, val2 in SOME_OPERANDS_COUPLES_16:
        for imm in SOME_OPERANDS_16:
            compare(tmpdir, asm % (val1, val2, imm), ["ecx", "ebx", "of", "cf"])

def test_imul_reg32(tmpdir):
    asm = """
            mov eax, %#x
            mov ebx, %#x
            imul ebx
          """
    for vals in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % vals, ["eax", "edx", "of", "cf"])

def test_movzx(tmpdir):
    asm = """
            mov eax, %i
            movzx bx, al
            movzx ecx, al
            movzx edx, ax
          """
    for val in [0, 1, 2, 0x7f, 0x7f, 0x80, 0x81, 0xff, 0x100, 0x101, 0x7fff, 0x8000, 0xffff ]:
        compare(tmpdir, asm % val, ["eax", "ebx", "ecx", "edx"])

def test_movsx(tmpdir):
    asm = """
            mov eax, %i
            movsx bx, al
            movsx ecx, al
            movsx edx, ax
          """
    for val in [0, 1, 2, 0x7f, 0x7f, 0x80, 0x81, 0xff, 0x100, 0x101, 0x7fff, 0x8000, 0xffff ]:
        compare(tmpdir, asm % val, ["eax", "ebx", "ecx", "edx"])


##  _    ___   ___  ___     __  ___ ___ ___     __   ___ ___  _  _ ___  
## | |  / _ \ / _ \| _ \   / / | _ \ __| _ \   / /  / __/ _ \| \| |   \ 
## | |_| (_) | (_) |  _/  / /  |   / _||  _/  / /  | (_| (_) | .` | |) |
## |____\___/ \___/|_|   /_/   |_|_\___|_|   /_/    \___\___/|_|\_|___/ 
##                                                                      
        
def test_repne_scasb(tmpdir):
    asm = """
            push 0x00006A69
            push 0x68676665
            push 0x64636261
            mov edi, esp
            xor al,al
            mov ecx, 0xffffffff
            cld
            repne scasb
            pushf
            sub edi, esp
            mov edx, ecx
            not edx
            popf
         """
    compare(tmpdir, asm, ["edi", "ecx", "edx", "zf", "cf", "of", "pf", "af", "sf"])


def test_repne_scasb_unknown_memory(tmpdir):
    asm = """
            mov edi, esp
            xor al,al
            mov ecx, 0xffffffff
            cld
            repne scasb
            pushf
            sub edi, esp
            mov edx, ecx
            not edx
            popf
         """
    compare(tmpdir, asm, ["edi", "ecx", "edx", "zf", "cf", "of", "pf", "af", "sf"])


def test_loop(tmpdir):
    asm = """
            mov ecx, 0x40
            mov eax, 0
         loop:
            inc eax
            loop loop
          """
    compare(tmpdir, asm, ["eax", "ecx", "zf", "of", "pf", "af", "sf"])


def test_cond_jump_jne(tmpdir):
    asm = """
            mov ecx, %i
            mov eax, 0
         loop:
            inc eax
            dec ecx
            cmp ecx,0
            jne loop
          """
    for i in range(1, 20):
        compare(tmpdir, asm % i, ["eax", "ecx", "zf", "cf", "of", "pf", "af", "sf"])


##  ___ ___ _____   _____ ___ ___ _____ ___ _  _  ___ 
## | _ )_ _|_   _| |_   _| __/ __|_   _|_ _| \| |/ __|
## | _ \| |  | |     | | | _|\__ \ | |  | || .` | (_ |
## |___/___| |_|     |_| |___|___/ |_| |___|_|\_|\___|
##                                                    

def test_bittest_bt_reg32(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            bt eax, ebx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_bt_reg16(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            bt ax, bx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_bt_imm8(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            bt eax, %i
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "cf"])


def test_bittest_bts_reg32(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            bts eax, ebx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_bts_reg16(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            bts ax, bx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_bts_imm8(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            bts eax, %i
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])


def test_bittest_btr_reg32(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            btr eax, ebx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_btr_reg16(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            btr ax, bx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_btr_imm8(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            btr eax, %i
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])


def test_bittest_btc_reg32(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            btc eax,ebx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_btc_reg16(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            mov ebx, %i
            btc ax, bx
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_btc_imm8(tmpdir):
    asm = """
            mov eax, 0xA35272F4
            btc eax, %i
    """
    for i in SOME_SHIFT_COUNTS:
        compare(tmpdir, asm % i, ["eax", "ebx", "cf"])

def test_bittest_bsr_reg32(tmpdir):
    asm = """
            mov eax, %#x
            xor ebx, ebx
            bsr ebx, eax
    """
    for i in SOME_OPERANDS:
        compare(tmpdir, asm % i, ["eax", "ebx", "zf"])

def test_bittest_bsr_m32(tmpdir):
    asm = """
            push %#x
            xor ebx, ebx
            bsr ebx, [esp]
    """
    for i in SOME_OPERANDS:
        compare(tmpdir, asm % i, ["ebx", "zf"])


def test_bittest_bsr_reg16(tmpdir):
    asm = """
            mov eax, %#x
            xor ebx, ebx
            bsr bx, ax
    """
    for i in SOME_OPERANDS_16:
        compare(tmpdir, asm % i, ["eax", "ebx", "zf"])

def test_bittest_bsf_reg32(tmpdir):
    asm = """
            mov eax, %#x
            xor ebx, ebx
            bsf ebx, eax
    """
    for i in SOME_OPERANDS:
        compare(tmpdir, asm % i, ["eax", "ebx", "zf"])

def test_bittest_bsf_m32(tmpdir):
    asm = """
            push %#x
            xor ebx, ebx
            bsf ebx, [esp]
    """
    for i in SOME_OPERANDS:
        compare(tmpdir, asm % i, ["ebx", "zf"])


def test_bittest_bsf_reg16(tmpdir):
    asm = """
            mov eax, %#x
            xor ebx, ebx
            bsf bx, ax
    """
    for i in SOME_OPERANDS_16:
        compare(tmpdir, asm % i, ["eax", "ebx", "zf"])


##  __  __ ___ ___  ___ 
## |  \/  |_ _/ __|/ __|
## | |\/| || |\__ \ (__ 
## |_|  |_|___|___/\___|
##                      

def test_pushf_popf(tmpdir):
    asm = """
            stc
            mov eax, 0x7fffffff
            mov ebx, 0x7fffffff
            pushf
            popf
            adc ax, bx
          """
    compare(tmpdir, asm, ["eax", "of", "sf", "zf", "cf", "pf", "af"])


def test_xlat(tmpdir):
    asm = """
            mov ecx, 64
         loop:
            mov eax, 0x01020304
            mul ecx
            push eax
            dec ecx
            jnz loop
            mov ebx, esp
            mov eax, 0xf214cb00
            mov al, %#x
            xlat
          """
    for i in SOME_OPERANDS_8:
        compare(tmpdir, asm % i, ["eax"])

def test_xchg_m32_r32(tmpdir):
    asm = """
           push 0x12345678
           push 0xabcdef12
           mov eax, 0x87654321
           xchg [esp+4], eax
           pop ebx
           pop ecx
         """
    compare(tmpdir, asm, ["eax", "ebx", "ecx"])

def test_xchg_m8_r8(tmpdir):
    asm = """
           push 0x12345678
           push 0xabcdef12
           mov eax, 0x87654321
           xchg [esp+4], al
           pop ebx
           pop ecx
         """
    compare(tmpdir, asm, ["eax", "ebx", "ecx"])

def test_xchg_r32_r32(tmpdir):
    asm = """
           mov eax, 0x12345678
           mov ebx, 0x87654321
           xchg eax, ebx
         """
    compare(tmpdir, asm, ["eax", "ebx"])

def test_cmpxchg_r32_r32(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           mov ecx, %#x
           cmpxchg ebx, ecx
         """
    vals = [0x12345678, 0x9abcdef0, 0x87654321]
    for v in itertools.product(vals, vals, vals):
        compare(tmpdir, asm % v, ["eax", "ebx", "ecx", "zf"])

def test_cmpxchg_r16_r16(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           mov ecx, %#x
           cmpxchg bx, cx
         """
    vals = [0x12345678, 0x9abcdef0, 0x87654321]
    for v in itertools.product(vals, vals, vals):
        compare(tmpdir, asm % v, ["eax", "ebx", "ecx", "zf"])

def test_cmpxchg_r8_r8(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           mov ecx, %#x
           cmpxchg bl, cl
         """
    vals = [0x12345678, 0x9abcdef0, 0x87654321]
    for v in itertools.product(vals, vals, vals):
        compare(tmpdir, asm % v, ["eax", "ebx", "ecx", "zf"])

def test_cmpxchg_m32_r32(tmpdir):
    asm = """
           mov eax, %#x
           push 0
           push %#x
           mov ecx, %#x
           cmpxchg [esp+4], ecx
           pop ebx
           pop ebx
         """
    vals = [0x12345678, 0x9abcdef0, 0x87654321]
    for v in itertools.product(vals, vals, vals):
        compare(tmpdir, asm % v, ["eax", "ebx", "ecx", "zf"])

def test_cmpxchg8b_posofs(tmpdir):
    # keep order of registers so that edx:eax <- v1, ecx:ebx <- v2 and [esp+4] <- v3
    asm = """
           mov edx, %#x
           mov eax, %#x
           mov ecx, %#x
           mov ebx, %#x
           push %#x
           push %#x
           push 0
           cmpxchg8b [esp+4]
           pop esi
           pop esi
           pop edi
         """
    vals = [0x123456789abcdef0, 0xfecdba876543210,0xa5a5a5a56c6c6c6c]
    for v1,v2,v3 in itertools.product(vals, vals, vals, ):
        compare(tmpdir, asm % (v1>>32,v1&0xffffffff, v2>>32,v2&0xffffffff,v3>>32,v3&0xffffffff),
                ["eax", "ebx", "ecx", "edx", "esi", "edi", "zf"])

def test_cmpxchg8b_negofs(tmpdir):
    # keep order of registers so that edx:eax <- v1, ecx:ebx <- v2 and [esp+4] <- v3
    asm = """
           mov esi, esp
           mov edx, %#x
           mov eax, %#x
           mov ecx, %#x
           mov ebx, %#x
           push %#x
           push %#x
           cmpxchg8b [esi-8]
           pop esi
           pop edi
         """
    vals = [0x123456789abcdef0, 0xfecdba876543210,0xa5a5a5a56c6c6c6c]
    for v1,v2,v3 in itertools.product(vals, vals, vals, ):
        compare(tmpdir, asm % (v1>>32,v1&0xffffffff, v2>>32,v2&0xffffffff,v3>>32,v3&0xffffffff),
                ["eax", "ebx", "ecx", "edx", "esi", "edi", "zf"])

def test_xadd_r32_r32(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           xadd eax, ebx
         """
    for v in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % v, ["eax", "ebx"])

def test_xadd_r16_r16(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           xadd ax, bx
         """
    for v in SOME_OPERANDS_COUPLES_16:
        compare(tmpdir, asm % v, ["eax", "ebx"])

def test_xadd_r8_r8(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           xadd al, bl
         """
    for v in SOME_OPERANDS_COUPLES_8:
        compare(tmpdir, asm % v, ["eax", "ebx"])

def test_xadd_m32_r32(tmpdir):
    asm = """
           push 0
           push %#x
           mov ebx, %#x
           xadd [esp+4], ebx
           pop eax
           pop eax
         """
    for v in SOME_OPERANDS_COUPLES:
        compare(tmpdir, asm % v, ["eax", "ebx"])



def test_mov_rm32_r32(tmpdir):
    asm = """
           push 0x12345678
           push 0xabcdef12
           mov eax, 0x87654321
           mov [esp+4], eax
           pop ebx
           pop ecx
         """
    compare(tmpdir, asm, ["eax", "ebx", "ecx", "of"])

def test_mov_rm8_r8(tmpdir):
    asm = """
           push 0x12345678
           push 0xabcdef12
           mov eax, 0x87654321
           mov [esp+4], al
           pop ebx
           pop ecx
         """
    compare(tmpdir, asm, ["eax", "ebx", "ecx", "of"])


##  ___  ___ ___  
## | _ )/ __|   \ 
## | _ \ (__| |) |
## |___/\___|___/ 
##                

def test_bcd_daa(tmpdir):
    asm = """
           mov eax, %#x
           add eax, %#x
           daa
          """
    for a,b in SOME_OPERANDS_COUPLES_8:
        compare(tmpdir, asm % (a,b), ["eax", "cf", "af", "of"],
                top_allowed = { "of":1 })

def test_bcd_das(tmpdir):
    asm = """
           mov eax, %#x
           sub eax, %#x
           das
          """
    for a,b in SOME_OPERANDS_COUPLES_8:
        compare(tmpdir, asm % (a,b), ["eax", "cf", "af", "of"],
                top_allowed = { "of":1 })

def test_bcd_aaa(tmpdir):
    asm = """
           mov eax, %#x
           add ax, %#x
           aaa
          """
    for a,b in SOME_OPERANDS_COUPLES_8:
        compare(tmpdir, asm % (a,b), ["eax", "cf", "af", "of", "zf", "sf", "pf"],
                top_allowed = {"of":1, "sf":1, "zf":1, "pf":1 })

def test_bcd_aas(tmpdir):
    asm = """
           mov eax, %#x
           sub ax, %#x
           aas
          """
    for a,b in SOME_OPERANDS_COUPLES_8:
        compare(tmpdir, asm % (a,b), ["eax", "cf", "af", "of", "zf", "sf", "pf"],
                top_allowed = {"of":1, "sf":1, "zf":1, "pf":1 })

def test_bcd_aam(tmpdir):
    asm = """
           mov eax, %#x
           mov ebx, %#x
           mul bx
           aam %#x
          """
    for a,b in SOME_OPERANDS_COUPLES_8:
        for base in [10, 12, 8, 16, 0xff]:
            compare(tmpdir, asm % (a,b,base), ["eax", "cf", "af", "of", "zf", "sf", "pf"],
                    top_allowed = {"of":1, "af":1, "cf":1 })

def test_bcd_aad(tmpdir):
    asm = """
           mov eax, %#x
           aad %#x
          """
    for a in SOME_OPERANDS_16:
        for base in [10, 12, 8, 16, 0xff]:
            compare(tmpdir, asm % (a,base), ["eax", "sf", "zf", "pf", "of", "af", "cf"],
                    top_allowed = {"of":1, "af":1, "cf":1 })

def test_push_cs(tmpdir):
    asm = """
            push 0
            pop eax
            push cs
            pop eax
          """
    compare(tmpdir, asm, ["eax"])


def test_lea_imm(tmpdir):
    asm = """
            mov eax, 0
            mov ebx, 0
            mov ecx, 0
            lea eax, [0x124000]
            lea bx, [0x124000]
          """
    compare(tmpdir, asm, ["eax", "ebx", "ecx"])

