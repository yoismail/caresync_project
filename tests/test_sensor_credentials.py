import os
import unittest
from unittest.mock import patch

from python import sensor


class ConnectToDriveTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {"GOOGLE_DRIVE_SERVICE_ACCOUNT": '{"type": "service_account"}'},
    )
    @patch("python.sensor.build")
    @patch("python.sensor.service_account.Credentials.from_service_account_info")
    def test_uses_service_account_json_from_environment(
        self, from_service_account_info, build
    ):
        sensor.connect_to_drive()

        from_service_account_info.assert_called_once_with(
            {"type": "service_account"}, scopes=sensor.SCOPES
        )
        build.assert_called_once_with(
            "drive", "v3", credentials=from_service_account_info.return_value
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("python.sensor.build")
    @patch("python.sensor.service_account.Credentials.from_service_account_file")
    def test_falls_back_to_local_service_account_file(
        self, from_service_account_file, build
    ):
        sensor.connect_to_drive()

        from_service_account_file.assert_called_once_with(
            "service-account-key.json", scopes=sensor.SCOPES
        )
        build.assert_called_once_with(
            "drive", "v3", credentials=from_service_account_file.return_value
        )


if __name__ == "__main__":
    unittest.main()
