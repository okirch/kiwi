from nose.tools import *
from mock import patch
from mock import call
import mock
import kiwi

from . import nose_helper

from kiwi.container_builder import ContainerBuilder


class TestContainerBuilder(object):
    @patch('platform.machine')
    def setup(self, mock_machine):
        mock_machine.return_value = 'x86_64'
        xml_state = mock.Mock()
        xml_state.build_type.get_container = mock.Mock(
            return_value='my-container'
        )
        xml_state.get_image_version = mock.Mock(
            return_value='1.2.3'
        )
        xml_state.get_build_type_name = mock.Mock(
            return_value='docker'
        )
        xml_state.xml_data.get_name = mock.Mock(
            return_value='image_name'
        )
        self.setup = mock.Mock()
        kiwi.container_builder.SystemSetup = mock.Mock(
            return_value=self.setup
        )
        self.container = ContainerBuilder(
            xml_state, 'target_dir', 'root_dir'
        )
        self.container.result = mock.Mock()

    @patch('kiwi.container_builder.ContainerSetup')
    @patch('kiwi.container_builder.ContainerImage')
    def test_create(self, mock_image, mock_setup):
        container_setup = mock.Mock()
        mock_setup.return_value = container_setup
        container_image = mock.Mock()
        mock_image.return_value = container_image
        self.setup.export_rpm_package_verification.return_value = '.verified'
        self.setup.export_rpm_package_list.return_value = '.packages'
        self.container.create()
        mock_setup.assert_called_once_with(
            'docker', 'root_dir', {'container_name': 'my-container'}
        )
        container_setup.setup.assert_called_once_with()
        mock_image.assert_called_once_with(
            'docker', 'root_dir'
        )
        container_image.create.assert_called_once_with(
            'target_dir/image_name.x86_64-1.2.3.docker.tar.xz'
        )
        assert self.container.result.add.call_args_list == [
            call(
                'container',
                'target_dir/image_name.x86_64-1.2.3.docker.tar.xz'
            ),
            call(
                'image_packages',
                self.setup.export_rpm_package_list.return_value
            ),
            call(
                'image_verified',
                self.setup.export_rpm_package_verification.return_value
            )
        ]
        self.setup.export_rpm_package_verification.assert_called_once_with(
            'target_dir'
        )
        self.setup.export_rpm_package_list.assert_called_once_with(
            'target_dir'
        )
