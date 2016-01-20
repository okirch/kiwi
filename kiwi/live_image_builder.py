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
from tempfile import mkdtemp
import platform

# project
from bootloader_config import BootLoaderConfig
from filesystem import FileSystem
from filesystem_isofs import FileSystemIsoFs
from internal_boot_image_task import BootImageTask
from system_size import SystemSize
from firmware import FirmWare
from defaults import Defaults
from path import Path
from result import Result
from iso import Iso
from image_identifier import ImageIdentifier
from kernel import Kernel
from command import Command
from logger import log

from exceptions import (
    KiwiLiveBootImageError
)


class LiveImageBuilder(object):
    """
        Live image builder
    """
    def __init__(self, xml_state, target_dir, root_dir):
        self.media_dir = None
        self.arch = platform.machine()
        self.root_dir = root_dir
        self.target_dir = target_dir
        self.xml_state = xml_state
        self.live_type = xml_state.build_type.get_flags()
        self.types = Defaults.get_live_iso_types()
        self.hybrid = xml_state.build_type.get_hybrid()
        self.volume_id = xml_state.build_type.get_volid()
        self.machine = xml_state.get_build_type_machine_section()
        self.mbrid = ImageIdentifier()
        self.mbrid.calculate_id()

        if not self.live_type:
            self.live_type = Defaults.get_default_live_iso_type()

        self.boot_image_task = BootImageTask(
            xml_state, target_dir
        )
        self.firmware = FirmWare(
            xml_state
        )
        self.isoname = ''.join(
            [
                target_dir, '/',
                xml_state.xml_data.get_name(), '.iso'
            ]
        )
        self.live_image_file = ''.join(
            [
                target_dir, '/',
                xml_state.xml_data.get_name(),
                '-read-only.', self.arch, '-',
                xml_state.get_image_version()
            ]
        )
        self.result = Result()

    def create(self):
        if not self.boot_image_task.required():
            raise KiwiLiveBootImageError(
                'live images requires a boot setup in the type definition'
            )

        # media dir to store CD contents
        self.media_dir = mkdtemp(
            prefix='live-media.', dir=self.target_dir
        )
        rootsize = SystemSize(self.media_dir)

        # custom iso metadata
        log.info('Using following live ISO metadata:')
        log.info('--> Application id: %s', self.mbrid.get_id())
        log.info('--> Publisher: %s', Defaults.get_publisher())
        custom_iso_args = [
            '-A', self.mbrid.get_id(),
            '-p', '"' + Defaults.get_preparer() + '"',
            '-publisher', '"' + Defaults.get_publisher() + '"',
        ]
        if self.volume_id:
            log.info('--> Volume id: %s', self.volume_id)
            custom_iso_args.append('-V')
            custom_iso_args.append('"' + self.volume_id + '"')

        # prepare boot(initrd) root system
        log.info('Preparing live ISO boot system')
        self.boot_image_task.prepare()

        # pack system into live boot structure
        log.info('Packing system into live ISO type: %s', self.live_type)
        if self.live_type in self.types:
            live_type_image = FileSystem(
                name=self.types[self.live_type],
                device_provider=None,
                root_dir=self.root_dir
            )
            live_type_image.create_on_file(self.live_image_file)
            Command.run(
                ['mv', self.live_image_file, self.media_dir]
            )
            self.__create_live_iso_client_config(self.live_type)
        else:
            raise KiwiLiveBootImageError(
                'live ISO type "%s" not supported' % self.live_type
            )

        # setup bootloader config to boot the ISO via isolinux
        log.info('Setting up isolinux bootloader configuration')
        bootloader_config_isolinux = BootLoaderConfig(
            'isolinux', self.xml_state, self.media_dir
        )
        bootloader_config_isolinux.setup_live_boot_images(
            mbrid=None,
            lookup_path=self.boot_image_task.boot_root_directory
        )
        bootloader_config_isolinux.setup_live_image_config(
            mbrid=None
        )
        bootloader_config_isolinux.write()

        # setup bootloader config to boot the ISO via EFI
        if self.firmware.efi_mode():
            log.info('Setting up EFI grub bootloader configuration')
            bootloader_config_grub = BootLoaderConfig(
                'grub2', self.xml_state, self.media_dir
            )
            bootloader_config_grub.setup_live_boot_images(
                mbrid=self.mbrid,
                lookup_path=self.boot_image_task.boot_root_directory
            )
            bootloader_config_grub.setup_live_image_config(
                mbrid=self.mbrid
            )
            bootloader_config_grub.write()

        # create initrd for live image
        log.info('Creating live ISO boot image')
        self.__create_live_iso_kernel_and_initrd()

        # calculate size and decide if we need UDF
        if rootsize.accumulate_mbyte_file_sizes() > 4096:
            log.info('ISO exceeds 4G size, using UDF filesystem')
            custom_iso_args.append('-allow-limited-size')
            custom_iso_args.append('-udf')

        # create iso filesystem from media_dir
        log.info('Creating live ISO image')
        iso_image = FileSystemIsoFs(
            device_provider=None,
            root_dir=self.media_dir,
            custom_args=custom_iso_args
        )
        iso_header_offset = iso_image.create_on_file(self.isoname)

        # make it hybrid
        if self.hybrid:
            Iso.create_hybrid(
                iso_header_offset, self.mbrid, self.isoname
            )

        self.result.add(
            'live_image', self.isoname
        )
        return self.result

    def __create_live_iso_kernel_and_initrd(self):
        boot_path = self.media_dir + '/boot/x86_64/loader'
        Path.create(boot_path)
        kernel = Kernel(self.boot_image_task.boot_root_directory)
        if kernel.get_kernel():
            kernel.copy_kernel(boot_path, '/linux')
        else:
            raise KiwiLiveBootImageError(
                'No kernel in boot image tree %s found' %
                self.boot_image_task.boot_root_directory
            )
        if self.machine and self.machine.get_domain() == 'dom0':
            if kernel.get_xen_hypervisor():
                kernel.copy_xen_hypervisor(boot_path, '/xen.gz')
            else:
                raise KiwiLiveBootImageError(
                    'No hypervisor in boot image tree %s found' %
                    self.boot_image_task.boot_root_directory
                )
        self.boot_image_task.create_initrd(self.mbrid)
        Command.run(
            [
                'mv', self.boot_image_task.initrd_filename,
                boot_path + '/initrd'
            ]
        )

    def __create_live_iso_client_config(self, iso_type):
        """
            Setup IMAGE and UNIONFS_CONFIG variables as they are used in
            the kiwi isoboot code. Variable contents:

            + IMAGE=target_device;live_iso_name_definition
            + UNIONFS_CONFIG=rw_device,ro_device,union_type

            If no real block device is used or can be predefined the
            word 'loop' is set as a placeholder or indicator to use a loop
            device. For more details please refer to the kiwi shell boot
            code
        """
        iso_client_config_file = self.media_dir + '/config.isoclient'
        iso_client_params = Defaults.get_live_iso_client_parameters()
        (system_device, union_device, union_type) = iso_client_params[iso_type]

        with open(iso_client_config_file, 'w') as config:
            config.write(
                'IMAGE="%s;%s.%s;%s"\n' % (
                    system_device,
                    self.xml_state.xml_data.get_name(), self.arch,
                    self.xml_state.get_image_version()
                )
            )
            config.write(
                'UNIONFS_CONFIG="%s,loop,%s"\n' %
                (union_device, union_type)
            )

    def __del__(self):
        if self.media_dir:
            log.info('Cleaning up %s instance', type(self).__name__)
            Path.wipe(self.media_dir)
