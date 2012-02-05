#
# Copyright (c) 2010 Christophe Varoqui <christophe.varoqui@free.fr>'
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
import os
import sys
import platform
import datetime
from rcUtilities import justcall, which
from rcUtilitiesWindows import get_registry_value
import rcAsset
import ctypes
import wmi

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint),
                ("dwMemoryLoad", ctypes.c_uint),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),]

    def __init__(self):
        # have to initialize this to the size of MEMORYSTATUSEX
        self.dwLength = 2*4 + 7*8     # size = 2 ints, 7 longs
        return super(MEMORYSTATUSEX, self).__init__()


class Asset(rcAsset.Asset):
    def __init__(self, node):
        self.w = wmi.WMI()
        rcAsset.Asset.__init__(self, node)
        self.memstat = MEMORYSTATUSEX()
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(self.memstat))

    def _get_mem_bytes(self):
        return str(self.memstat.ullTotalPhys // 1024 // 1024)

    def _get_mem_banks(self):
        return '0'

    def _get_mem_slots(self):
        return '0'

    def _get_os_vendor(self):
        return 'Microsoft'

    def _get_os_name(self):
        return 'Windows'

    def _get_os_release(self):
        v = sys.getwindowsversion()
        product = {
         1: 'Workstation',
         2: 'Domain Controller',
         3: 'Server',
        }
	s = platform.release()
	s = s.replace('Server', ' Server')
	s = s.replace('Workstation', ' Workstation')
	s += " %s" % v.service_pack
        return s

    def _get_os_kernel(self):
        v = sys.getwindowsversion()
        return ".".join(map(str, [v.major, v.minor, v.build]))

    def _get_os_arch(self):
        return platform.uname()[4]

    def _get_cpu_freq(self):
        c = wmi.WMI()
        for i in c.Win32_Processor():
            cpuspeed = i.MaxClockSpeed
        return str(cpuspeed)

    def _get_cpu_cores(self):
	n = len(self.w.Win32_Processor())
        return str(n)

    def _get_cpu_dies(self):
	n = len(self.w.Win32_Processor())
        return str(n)

    def _get_cpu_model(self):
        for i in self.w.Win32_Processor():
            cputype = i.Name
        return cputype

    def _get_serial(self):
        return 'Unknown'

    def _get_model(self):
	key = ["HKEY_LOCAL_MACHINE", "SYSTEM\\CurrentControlSet\\Control\\SystemInformation", "SystemProductName"]
	#key = "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\OEMInformation"
	#key = "HKEY_LOCAL_MACHINE\DESCRIPTION\SYSTEM\BIOS"
	compname = get_registry_value(*key)
        return compname

    def _get_hba(self):
        return []

    def _get_targets(self):
        return []

