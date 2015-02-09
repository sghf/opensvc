#!/bin/bash

PATH_SCRIPT="$(cd $(/usr/bin/dirname $(type -p -- $0 || echo $0));pwd)"
PATH_LIB=$PATH_SCRIPT/com.opensvc
PREFIX=OSVC_COMP_FOO

typeset -i r=0

case $1 in
check)
	$PATH_LIB/files.py ${PREFIX}_FILES check
	[ $? -eq 1 ] && r=1
	$PATH_LIB/packages.py ${PREFIX}_PKG check
	[ $? -eq 1 ] && r=1
	exit $r
	;;
fix)
	$PATH_LIB/files.py ${PREFIX}_FILES fix
	[ $? -eq 1 ] && exit 1
	$PATH_LIB/packages.py ${PREFIX}_PKG fix
	[ $? -eq 1 ] && exit 1
	exit 0
	;;
fixable)
	exit 2
	;;
esac

