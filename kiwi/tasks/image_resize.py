# Copyright (c) 2015 SUSE Linux GmbH.  All rights reserved.
#
# This file is part of kiwi.
#
# kiwi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# kiwi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with kiwi.  If not, see <http://www.gnu.org/licenses/>
#
"""
usage: kiwi image resize -h | --help
       kiwi image resize --target-dir=<directory> --size=<size>
           [--root=<directory>]
       kiwi image resize help

commands:
    resize
        for disk based images, allow to resize the image to a new
        disk geometry. The additional space is free and not in use
        by the image. In order to make use of the additional free
        space a repartition process is required like it is provided
        by kiwi's oem boot code. Therefore the resize operation is
        useful for oem image builds most of the time

options:
    --root=<directory>
        the path to the root directory, if not specified kiwi
        searches the root directory in build/image-root below
        the specified target directory

    --size=<size>
        new size of the image. The value is either a size in bytes
        or can be specified with m=MB or g=GB. Example: 20g

    --target-dir=<directory>
        the target directory to expect image build results
"""
import re
import math

# project
from .base import CliTask
from ..help import Help
from ..logger import log
from ..storage.subformat import DiskFormat

from ..exceptions import (
    KiwiImageResizeError
)


class ImageResizeTask(CliTask):
    """
    Implements resizing of disk images and their disk format

    Attributes

    * :attr:`manual`
        Instance of Help
    """
    def process(self):
        """
        reformats raw disk image and its format to a new disk
        geometry using the qemu tool chain
        """
        self.manual = Help()
        if self.command_args.get('help') is True:
            return self.manual.show('kiwi::image::resize')

        if self.command_args['--root']:
            image_root = self.command_args['--root']
        else:
            image_root = ''.join(
                [self.command_args['--target-dir'], '/build/image-root']
            )

        self.load_xml_description(
            image_root
        )

        disk_format = self.xml_state.build_type.get_format()

        image_format = DiskFormat(
            disk_format or 'raw', self.xml_state, image_root,
            self.command_args['--target-dir']
        )
        if not image_format.has_raw_disk():
            raise KiwiImageResizeError(
                'no raw disk image %s found in build results' %
                image_format.diskname
            )

        new_disk_size = self._to_bytes(self.command_args['--size'])

        log.info(
            'Resizing raw disk to %d bytes', new_disk_size
        )
        resize_result = image_format.resize_raw_disk(new_disk_size)
        if disk_format and resize_result is True:
            log.info(
                'Creating %s disk format from resized raw disk', disk_format
            )
            image_format.create_image_format()
        elif resize_result is False:
            log.info(
                'Raw disk is already at %d bytes', new_disk_size
            )

    def _to_bytes(self, size_value):
        size_format = '^(\d+)([gGmM]{0,1})$'
        size = re.search(size_format, size_value)
        if not size:
            raise KiwiImageResizeError(
                'unsupported size format %s, must match %s' %
                (size_value, size_format)
            )
        size_base = int(size.group(1))
        size_unit = {'g': 3, 'm': 2}.get(size.group(2).lower())
        return size_unit and size_base * math.pow(0x400, size_unit) or size_base
