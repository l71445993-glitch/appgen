#!/bin/sh
set -e

mkdir -p /opt/rdgen/data /opt/rdgen/exe /opt/rdgen/png /opt/rdgen/temp_zips
chown -R user:user /opt/rdgen/data /opt/rdgen/exe /opt/rdgen/png /opt/rdgen/temp_zips

su-exec user python manage.py migrate --noinput

exec su-exec user "$@"
