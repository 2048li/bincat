import pytest
import os
from util import ARM

arm = ARM(
    os.path.join(os.path.dirname(os.path.realpath(__file__)),'armv7_isn.ini.in')
)
compare = arm.compare


def test_nop(tmpdir):
    asm = """
        mov r0,r0
    """
    compare(tmpdir, asm, [])


def test_assign(tmpdir):
    asm = """
        mov r0, #0x12
        mov r1, r0
        mov r2, r1
    """
    compare(tmpdir, asm, ["r0","r1", "r2"])



##  ___   _ _____ _     ___ ___  ___   ___ 
## |   \ /_\_   _/_\   | _ \ _ \/ _ \ / __|
## | |) / _ \| |/ _ \  |  _/   / (_) | (__ 
## |___/_/ \_\_/_/ \_\ |_| |_|_\\___/ \___|
## 
## DATA PROC

def test_mov_reg(tmpdir):
    asm = """
            mov r0, #0x12
            movs r1, r0
    """
    compare(tmpdir, asm, ["r0","r1", "z"])

def test_mov_set_zflag(tmpdir):
    asm = """
            mov r1, #0
            mov r2, #0
            mov r3, #0
            mov r4, #0
            movs r0, #0x12
            moveq r1, #1
            movne r2, #1
            movs r0, #0
            moveq r3, #1
            movne r4, #1
    """
    compare(tmpdir, asm, ["r0","r1","r2","r3", "r4", "n", "z"])

def test_mov_set_vflag(tmpdir):
    asm = """
            mov r1, #0
            mov r2, #0
            mov r3, #0
            mov r4, #0
            movs r0, #0x12
            movmi r1, #1
            movpl r2, #1
            movs r0, #0x80000000
            movmi r3, #1
            movpl r4, #1
    """
    compare(tmpdir, asm, ["r0","r1","r2","r3", "r4", "n", "z"])
