#
# Copyright (c) 2009 Christophe Varoqui <christophe.varoqui@free.fr>'
# Copyright (c) 2009 Cyril Galibern <cyril.galibern@free.fr>'
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
import ConfigParser
import logging

from rcGlobalEnv import *
from rcNode import discover_node
import rcOptParser
import rcLogger
import rcAddService

def svcmode_mod_name():
	if rcEnv.svcmode == 'lxc':
		return 'rcLXC'
	elif rcEnv.svcmode == 'hosted':
		return 'rcHosted'
	return 1 # raise something instead ?

def add_ips(self):
	rcEnv.ips = []
	for s in rcEnv.conf.sections():
		if 'ip' in s:
			ipname = rcEnv.conf.get(s, "ipname")
			ipdev = rcEnv.conf.get(s, "ipdev")
			self.add_ip(ipname, ipdev)

def add_filesystems(self):
	rcEnv.filesystems = []
	for s in rcEnv.conf.sections():
		if 'fs' in s:
			dev = rcEnv.conf.get(s, "dev")
			mnt = rcEnv.conf.get(s, "mnt")
			type = rcEnv.conf.get(s, "type")
			mnt_opt = rcEnv.conf.get(s, "mnt_opt")
			self.add_filesystem(dev, mnt, type, mnt_opt)

def install_actions():
	"""Setup the class svc methods as per node capabilities and
	service configuration.
	"""
	if rcEnv.svcmode == "hosted":
		rcEnv.do = rcEnv.rcMode.do()
	elif rcEnv.svcmode == "lxc":
		rcEnv.do = rcLXC.lxc_do()

	rcEnv.actions = rcEnv.do.__dict__.keys()
	rcEnv.actions.sort()
	return 0

def setup_logging():
	"""Setup logging to stream + logfile, and logfile rotation
	class Logger instance name: 'log'
	"""
	logging.setLoggerClass(rcLogger.Logger)
	global log
	log = logging.getLogger('INIT')
	if '--debug' in sys.argv:
		rcEnv.loglevel = logging.DEBUG
		log.setLevel(logging.DEBUG)
	elif '--warn' in sys.argv:
		rcEnv.loglevel = logging.WARNING
		log.setLevel(logging.WARNING)
	elif '--error' in sys.argv:
		rcEnv.loglevel = logging.ERROR
		log.setLevel(logging.ERROR)
	else:
		rcEnv.loglevel = logging.INFO
		log.setLevel(logging.INFO)


class svc():
	"""This base class exposes actions available to all type of services,
	like stop, start, ...
	It's meant to be enriched by inheriting class for specialized services,
	like LXC containers, ...
	"""
	def add_ip(self, ipname, ipdev):
		log = logging.getLogger('INIT')
		ip = rcEnv.rcMode.Ip(ipname, ipdev)
		if ip is None:
			log.error("initialization failed for ip (%s@%s)" %
				 (ipname, ipdev))
			return 1
		log.debug("initialization succeeded for ip (%s@%s)" %
			 (ipname, ipdev))
		rcEnv.ips.append(ip)

	def add_filesystem(self, dev, mnt, type, mnt_opt):
		log = logging.getLogger('INIT')
		fs = rcEnv.rcMode.Filesystem(dev, mnt, type, mnt_opt)
		if fs is None:
			log.error("initialization failed for fs (%s %s %s %s)" %
				 (dev, mnt, type, mnt_opt))
			return 1
		log.debug("initialization succeeded for fs (%s %s %s %s)" %
			 (dev, mnt, type, mnt_opt))
		rcEnv.filesystems.append(fs)

	def __init__(self, name):
		#
		# file tree abstraction
		#
		rcEnv.pathsvc = os.path.realpath(os.path.dirname(__file__) + "/..")
		rcEnv.pathbin = rcEnv.pathsvc + "/bin"
		rcEnv.pathetc = rcEnv.pathsvc + "/etc"
		rcEnv.pathlib = rcEnv.pathsvc + "/lib"
		rcEnv.pathlog = rcEnv.pathsvc + "/log"
		rcEnv.pathtmp = rcEnv.pathsvc + "/tmp"
		rcEnv.pathvar = rcEnv.pathsvc + "/var"
		rcEnv.logfile = rcEnv.pathlog + '/' + rcEnv.svcname + '.log'
		rcEnv.svcconf = rcEnv.pathetc + "/" + rcEnv.svcname + ".env"
		rcEnv.svcinitd = rcEnv.pathetc + "/" + rcEnv.svcname + ".d"
		rcEnv.sysname, rcEnv.nodename, x, x, rcEnv.machine = os.uname()

		setup_logging()
		if name == "rcService":
			log.error("do not execute rcService directly")
			return None

		#
		# print stuff we determined so far
		#
		log.debug('sysname = ' + rcEnv.sysname)
		log.debug('nodename = ' + rcEnv.nodename)
		log.debug('machine = ' + rcEnv.machine)
                log.debug('pathsvc = ' + rcEnv.pathsvc)
                log.debug('pathbin = ' + rcEnv.pathbin)
                log.debug('pathetc = ' + rcEnv.pathetc)
                log.debug('pathlib = ' + rcEnv.pathlib)
                log.debug('pathlog = ' + rcEnv.pathlog)
                log.debug('pathtmp = ' + rcEnv.pathtmp)
		log.debug('service name = ' + rcEnv.svcname)
		log.debug('service config file = ' + rcEnv.svcconf)
                log.debug('service log file = ' + rcEnv.logfile)
                log.debug('service init dir = ' + rcEnv.svcinitd)

		#
		# node discovery is hidden in a separate module to
		# keep it separate from the framework stuff
		#
		discover_node()

		#
		# parse service configuration file
		# class RawConfigParser instance name: 'conf'
		#
		rcEnv.svcmode = "hosted"
		if os.path.isfile(rcEnv.svcconf):
			rcEnv.conf = ConfigParser.RawConfigParser()
			rcEnv.conf.read(rcEnv.svcconf)
			if rcEnv.conf.has_option("default", "mode"):
				rcEnv.svcmode = conf.get("default", "mode")

		log.debug('service mode = ' + rcEnv.svcmode)
		rcEnv.rcMode = __import__(svcmode_mod_name(), globals(), locals(), [], -1)

		if install_actions() != 0: return None

		log.debug('service supported actions = ' + str(rcEnv.actions))

		#
		# parse command line
		# class svcOptionParser instance name: 'parser'
		#
		self.parser = rcOptParser.svcOptionParser()

		add_ips(self)
		add_filesystems(self)
		#
		# instanciate appropiate actions class
		# class do instance name: 'do'
		#
		getattr(rcEnv.do, self.parser.action)()

