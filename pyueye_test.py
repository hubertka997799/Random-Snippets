import configparser
from tkinter.constants import NS
from numpy.core.memmap import memmap
from pyueye import ueye
import ctypes
from ctypes import c_uint, c_int, sizeof

# init camera
camera = ueye.HIDS(0)
ret = ueye.is_InitCamera(camera, None)

# save/load parameter to file or camera's EEPROM
'''
# save/load parameter(.ini) (from/to) current camera setting
nRet = ueye.is_ParameterSet(camera, ueye.IS_PARAMETERSET_CMD_SAVE_FILE, ctypes.c_wchar_p("t1.ini"), c_uint(0))
nRet = ueye.is_ParameterSet(camera, ueye.IS_PARAMETERSET_CMD_LOAD_FILE, ctypes.c_wchar_p("1223.ini"), c_uint(0))
# save/load EEPROM function's parameter only (comes from/goes to) current camera setting, you can't directly interect with EEPROM
# e.g. IS_PARAMETERSET_CMD_SAVE_EEPROM => save current camera setting parameter to EEPROM
nRet = ueye.is_ParameterSet(camera, ueye.IS_PARAMETERSET_CMD_SAVE_EEPROM, c_uint(0), c_uint(0))
nRet = ueye.is_ParameterSet(camera, ueye.IS_PARAMETERSET_CMD_LOAD_EEPROM, c_uint(0), c_uint(0))
'''

# .ini to dict
'''
config = configparser.ConfigParser()
config.read('1223.ini', encoding='utf-8-sig')
print(list(config))
print(config['Parameters']['Colormode'])
'''

# get USER_EXTENDED_MEMORY size of current camera
'''
nSize = c_uint(0)
nRet = ueye.is_PersistentMemory(camera, ueye.IS_PERSISTENT_MEMORY_GET_SIZE_USER_EXTENDED, nSize, ctypes.sizeof(nSize))
if nRet:
    print('something goes wrong or your camera dosn''t have that 64K extra memory')
else:
    print('mem_size = ',nSize)
# TL;DR USER_EXTENDED_MEMORY=64*1024-1(byte) , USER_MEMORY=64(byte)
'''

# write/read USER_EXTENDED_MEMORY
'''
write_content = ctypes.create_string_buffer(10)  # create a string buffer with len=10
write_content.value = b'testing'  # set this sring as 'testing' with terminate char / NULL char / '\x00'
print(write_content.raw)
nPersistentMemory = ueye.IS_PERSISTENT_MEMORY()
nPersistentMemory.u32Offset = 0
nPersistentMemory.u32Count = sizeof(write_content)
nPersistentMemory.s32Option = 0
nPersistentMemory.pu8Memory = ctypes.cast(write_content, ueye.c_mem_p)
nRet = ueye.is_PersistentMemory(camera, ueye.IS_PERSISTENT_MEMORY_WRITE_USER_EXTENDED, nPersistentMemory, ctypes.sizeof(nPersistentMemory))
if not nRet:
    print('write success')


content = ctypes.create_string_buffer(10)  # create a string buffer with len=10
nPersistentMemory = ueye.IS_PERSISTENT_MEMORY()
nPersistentMemory.u32Offset = 0
nPersistentMemory.u32Count = sizeof(content)
nPersistentMemory.s32Option = 0
nPersistentMemory.pu8Memory = ctypes.cast(content, ueye.c_mem_p)
nRet = ueye.is_PersistentMemory(camera, ueye.IS_PERSISTENT_MEMORY_READ_USER_EXTENDED, nPersistentMemory, ctypes.sizeof(nPersistentMemory))
if not nRet:
    print('read success')

mem = ctypes.cast(nPersistentMemory.pu8Memory, ctypes.POINTER(ueye.c_char))

print(mem[:nPersistentMemory.u32Count.value], ' len=', nPersistentMemory.u32Count)
print(ctypes.cast(mem, ctypes.c_char_p).value)
'''
